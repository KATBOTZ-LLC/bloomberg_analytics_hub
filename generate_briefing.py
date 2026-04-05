#!/usr/bin/env python3
"""
CFO Pulse - Automated Narrative Briefing Generator
Pulls latest financial data from HANA, generates a 1-page CFO briefing via Claude/OpenAI,
and sends it via Gmail SMTP.

Usage:
    python generate_briefing.py

Runs once and exits. Schedule via cron for weekly delivery.
"""

import os
import sys
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from utils.config import load_config, setup_logging
from db.hana_client import HanaClient
from db.data_service import FinancialDataService as DataService

setup_logging()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. PULL DATA FROM HANA
# ─────────────────────────────────────────────

def pull_financial_data(data_service):
    """Pull key metrics from HANA for the briefing."""
    data = {}

    try:
        # Latest financial ratios (all tickers)
        ratios_df = data_service.get_financial_ratios(limit=100)
        if not ratios_df.empty:
            data['ratios'] = ratios_df

        # Summary stats
        stats = data_service.get_summary_stats()
        data['stats'] = stats

        # Top/bottom performers by gross margin
        if not ratios_df.empty and 'GROSS_MARGIN' in ratios_df.columns:
            sorted_df = ratios_df.dropna(subset=['GROSS_MARGIN']).sort_values('GROSS_MARGIN', ascending=False)
            data['top_margin'] = sorted_df.head(5)[['TICKER', 'GROSS_MARGIN', 'EBITDA_MARGIN']].to_dict('records')
            data['bottom_margin'] = sorted_df.tail(5)[['TICKER', 'GROSS_MARGIN', 'EBITDA_MARGIN']].to_dict('records')

        # Current ratio (liquidity)
        if not ratios_df.empty and 'CUR_RATIO' in ratios_df.columns:
            liq = ratios_df.dropna(subset=['CUR_RATIO'])
            data['avg_current_ratio'] = round(liq['CUR_RATIO'].mean(), 2)
            data['median_current_ratio'] = round(liq['CUR_RATIO'].median(), 2)

        # Debt metrics
        if not ratios_df.empty and 'TOT_DEBT_TO_EBITDA' in ratios_df.columns:
            debt = ratios_df.dropna(subset=['TOT_DEBT_TO_EBITDA'])
            data['avg_debt_ebitda'] = round(debt['TOT_DEBT_TO_EBITDA'].mean(), 2)

    except Exception as e:
        logger.error(f"Error pulling data: {e}")

    return data


# ─────────────────────────────────────────────
# 2. GENERATE NARRATIVE WITH LLM
# ─────────────────────────────────────────────

def generate_narrative(data):
    """Generate 1-page CFO briefing narrative using Claude or OpenAI."""

    # Build data summary for the prompt
    top = data.get('top_margin', [])
    bottom = data.get('bottom_margin', [])
    stats = data.get('stats', {})
    avg_cr = data.get('avg_current_ratio', 'N/A')
    avg_de = data.get('avg_debt_ebitda', 'N/A')

    top_str = '\n'.join([f"  - {j['TICKER']}: Gross Margin {j.get('GROSS_MARGIN','N/A'):.1f}%, EBITDA {j.get('EBITDA_MARGIN','N/A'):.1f}%" for j in top]) if top else "N/A"
    bottom_str = '\n'.join([f"  - {j['TICKER']}: Gross Margin {j.get('GROSS_MARGIN','N/A'):.1f}%, EBITDA {j.get('EBITDA_MARGIN','N/A'):.1f}%" for j in bottom]) if bottom else "N/A"

    prompt = f"""You are a senior financial analyst writing a concise, board-ready CFO briefing.

Today's date: {datetime.now().strftime('%B %d, %Y')}
Data covers: {stats.get('ratios_count', 'N/A')} companies tracked via Bloomberg

KEY METRICS THIS WEEK:
- Average Current Ratio (liquidity): {avg_cr}
- Average Debt/EBITDA: {avg_de}

TOP 5 COMPANIES BY GROSS MARGIN:
{top_str}

BOTTOM 5 COMPANIES BY GROSS MARGIN:
{bottom_str}

Write a 1-page CFO briefing (300-400 words) that:
1. Opens with a sharp 1-sentence executive summary of market conditions
2. Highlights profitability trends (who's winning, who's struggling and why)
3. Comments on liquidity and leverage across the peer group
4. Flags any anomalies worth investigating
5. Closes with 2-3 forward-looking strategic implications

Tone: Direct, professional, no fluff. Like a McKinsey partner wrote it.
Format: Plain paragraphs, no bullet points, board-ready."""

    # Try Anthropic Claude first
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        logger.warning(f"Claude failed: {e}, trying OpenAI...")

    # Fallback to OpenAI
    try:
        import openai
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"OpenAI failed: {e}, using fallback narrative...")

    # Fallback: simple template if no LLM available
    return f"""CFO PULSE WEEKLY BRIEFING — {datetime.now().strftime('%B %d, %Y')}

This week's analysis covers {stats.get('ratios_count', 'N/A')} companies tracked via Bloomberg Data License.

PROFITABILITY: The peer group shows varied margin performance. Top performers maintain gross margins above 60%, while bottom performers are under pressure. Average EBITDA margin divergence suggests structural cost differences across the group.

LIQUIDITY: The average current ratio of {avg_cr} indicates {('adequate' if float(avg_cr) > 1.5 else 'tight') if avg_cr != 'N/A' else 'variable'} short-term liquidity across the peer group. Companies below 1.0 warrant closer monitoring.

LEVERAGE: Average Debt/EBITDA of {avg_de} is {('elevated' if float(avg_de) > 3.0 else 'manageable') if avg_de != 'N/A' else 'variable'} relative to historical norms. Rising interest rates make this metric critical to track.

FORWARD OUTLOOK: Continue monitoring margin compression trends. Companies with strong free cash flow generation remain best positioned for the current environment.

— CFO Pulse | Automated Weekly Briefing"""


# ─────────────────────────────────────────────
# 3. SEND EMAIL VIA GMAIL SMTP
# ─────────────────────────────────────────────

def send_email(subject, narrative, recipients):
    """Send the briefing via Gmail SMTP."""
    gmail_sender = os.getenv('GMAIL_SENDER', 'alertcfo@katbotz.com')
    gmail_password = os.getenv('GMAIL_APP_PASSWORD', '')

    if not gmail_password:
        logger.error("GMAIL_APP_PASSWORD not set — cannot send email")
        print("\n" + "="*60)
        print("EMAIL NOT SENT (no Gmail credentials)")
        print("="*60)
        print(f"\nSubject: {subject}\n")
        print(narrative)
        return False

    # Build HTML email
    html_body = f"""
    <html><body style="font-family: Georgia, serif; max-width: 700px; margin: auto; padding: 20px;">
    <div style="border-bottom: 3px solid #1a1a2e; margin-bottom: 20px; padding-bottom: 10px;">
        <h2 style="color: #1a1a2e; margin: 0;">📊 CFO Pulse Weekly Briefing</h2>
        <p style="color: #666; margin: 5px 0 0;">{datetime.now().strftime('%B %d, %Y')} &nbsp;|&nbsp; Powered by Bloomberg + SAP HANA</p>
    </div>
    <div style="line-height: 1.8; color: #222; white-space: pre-wrap;">{narrative}</div>
    <div style="border-top: 1px solid #ddd; margin-top: 30px; padding-top: 15px; color: #999; font-size: 12px;">
        This briefing was auto-generated by CFO Pulse. 
        <a href="https://financial-dashboard.cfapps.us10-001.hana.ondemand.com" style="color: #1a1a2e;">View Dashboard</a>
    </div>
    </body></html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = gmail_sender
    msg['To'] = ', '.join(recipients)
    msg.attach(MIMEText(narrative, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_sender, gmail_password)
            server.sendmail(gmail_sender, recipients, msg.as_string())
        logger.info(f"Briefing sent to: {', '.join(recipients)}")
        print(f"✅ Email sent to: {', '.join(recipients)}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        print(f"❌ Email failed: {e}")
        print("\n--- BRIEFING CONTENT ---\n")
        print(narrative)
        return False


# ─────────────────────────────────────────────
# 4. MAIN
# ─────────────────────────────────────────────

def main():
    print("="*60)
    print("CFO PULSE — Automated Briefing Generator")
    print(f"Running: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # Load config
    config = load_config()

    # Connect to HANA
    print("\nConnecting to HANA...")
    hana_client = HanaClient(config)
    if not hana_client.connect():
        print("❌ Failed to connect to HANA. Check .env credentials.")
        sys.exit(1)
    print("✅ Connected to HANA")

    # Pull data
    print("\nPulling financial data...")
    data_service = DataService(hana_client)
    data = pull_financial_data(data_service)
    print(f"✅ Data pulled: {data.get('stats', {}).get('ratios_count', 0)} companies")

    # Generate narrative
    print("\nGenerating narrative...")
    narrative = generate_narrative(data)
    print("✅ Narrative generated")

    # Send email
    recipients = [
        r.strip() for r in os.getenv('NOTIFICATION_EMAILS', 'nikhilpr16@katbotz.com').split(',')
    ]
    subject = f"📊 CFO Pulse Weekly Briefing — {datetime.now().strftime('%B %d, %Y')}"

    print(f"\nSending email to: {', '.join(recipients)}")
    send_email(subject, narrative, recipients)

    hana_client.close()
    print("\n✅ Done!")


if __name__ == '__main__':
    main()
