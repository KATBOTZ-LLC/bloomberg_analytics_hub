# Bloomberg Financial Analytics Dashboard

Interactive web-based dashboard for visualizing financial data from SAP HANA Cloud. Built with Plotly Dash for real-time analytics and insights.

## Features

### Dashboard Views

1. **Overview Tab**
   - Distribution of key financial ratios (box plots)
   - Correlation heatmap for metric relationships
   - Top 10 companies by margin analysis
   - Liquidity and leverage analysis
   - Real-time summary statistics

2. **Financial Ratios Tab**
   - Company-specific ratio analysis
   - Interactive metric selection
   - Key liquidity and efficiency ratios

3. **Company Comparison**
   - Side-by-side comparison of 2-5 companies
   - Multiple metrics support
   - Visual benchmarking

4. **Data Explorer**
   - Raw data table view
   - Adjustable record limits

### Available Financial Metrics

- **Debt Ratios:** Total Debt to Asset, Total Debt to EBITDA, Net Debt to Shareholder Equity
- **Liquidity:** Current Ratio, Quick Ratio
- **Profitability:** Gross Margin, EBITDA Margin
- **Coverage:** Interest Coverage Ratio, Cash Dividend Coverage
- **Balance Sheet:** Total Liabilities and Equity

## Technology Stack

- **Framework:** Plotly Dash + Flask
- **Database:** SAP HANA Cloud
- **Visualization:** Plotly.js
- **UI Components:** Dash Bootstrap Components
- **Data Processing:** Pandas
- **Web Server:** Gunicorn

## Quick Start

### Prerequisites

- Python 3.8+
- Access to SAP HANA Cloud instance
- Cloud Foundry CLI (for deployment)

### Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd bloomberg_analytics_hub
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   Create a `.env` file:
   ```bash
   HANA_ADDRESS=<your-instance>.hana.ondemand.com
   HANA_PORT=443
   HANA_USER=<username>
   HANA_PASSWORD=<password>
   HANA_SCHEMA=BLOOMBERG_DATA
   HANA_TABLE=FINANCIAL_RATIOS
   ```

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the dashboard**
   ```
   http://localhost:8080
   ```

## Cloud Foundry Deployment

### Prerequisites

- Cloud Foundry account
- CF CLI installed
- HANA database instance running

### Deploy Steps

1. **Login to Cloud Foundry**
   ```bash
   cf login -a <api-endpoint>
   ```

2. **Update manifest.yml**

   Edit the HANA credentials in `manifest.yml` (or use environment variables):
   ```yaml
   env:
     HANA_ADDRESS: your-instance.hana.ondemand.com
     HANA_PORT: 443
     HANA_USER: DBADMIN
     HANA_PASSWORD: your_password
     HANA_SCHEMA: BLOOMBERG_DATA
   ```

3. **Push to Cloud Foundry**
   ```bash
   cf push
   ```

4. **Verify deployment**
   ```bash
   cf apps
   cf logs financial-dashboard --recent
   ```

### Using Environment Variables (Recommended)

Instead of hardcoding credentials in manifest.yml:

```bash
cf set-env financial-dashboard HANA_ADDRESS "your-instance.hana.ondemand.com"
cf set-env financial-dashboard HANA_PORT "443"
cf set-env financial-dashboard HANA_USER "DBADMIN"
cf set-env financial-dashboard HANA_PASSWORD "your_password"
cf set-env financial-dashboard HANA_SCHEMA "BLOOMBERG_DATA"
cf restage financial-dashboard
```

## Database Schema

The dashboard connects to a single table: `FINANCIAL_RATIOS`

### Table Structure

| Column Name | Type | Description |
|-------------|------|-------------|
| ID | INTEGER | Primary key |
| TICKER | NVARCHAR(50) | Stock ticker symbol |
| IDENTIFIER_TYPE | NVARCHAR(20) | Identifier type |
| IDENTIFIER_VALUE | NVARCHAR(100) | Identifier value |
| TOT_DEBT_TO_TOT_ASSET | DECIMAL(18,6) | Debt to asset ratio |
| CASH_DVD_COVERAGE | DECIMAL(18,6) | Cash dividend coverage |
| TOT_DEBT_TO_EBITDA | DECIMAL(18,6) | Debt to EBITDA ratio |
| CUR_RATIO | DECIMAL(18,6) | Current ratio |
| QUICK_RATIO | DECIMAL(18,6) | Quick ratio |
| GROSS_MARGIN | DECIMAL(18,6) | Gross profit margin |
| INTEREST_COVERAGE_RATIO | DECIMAL(18,6) | Interest coverage |
| EBITDA_MARGIN | DECIMAL(18,6) | EBITDA margin |
| TOT_LIAB_AND_EQY | DECIMAL(18,6) | Total liabilities & equity |
| NET_DEBT_TO_SHRHLDR_EQTY | DECIMAL(18,6) | Net debt to equity |
| TIMESTAMP | TIMESTAMP | Record timestamp |

## Project Structure

```
bloomberg_analytics_hub/
├── app.py                      # Main dashboard application
├── requirements.txt            # Python dependencies
├── manifest.yml               # Cloud Foundry configuration
├── Procfile                   # Process file for deployment
├── db/
│   ├── hana_client.py        # HANA database client
│   └── data_service.py       # Data access layer
├── utils/
│   └── config.py             # Configuration utilities
├── assets/
│   └── custom.css            # Dashboard styling
├── data/
│   └── identifiers.json      # Data configuration
└── logs/                      # Application logs
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| HANA_ADDRESS | Yes | - | HANA instance address |
| HANA_PORT | Yes | 443 | HANA connection port |
| HANA_USER | Yes | - | Database username |
| HANA_PASSWORD | Yes | - | Database password |
| HANA_SCHEMA | Yes | BLOOMBERG_DATA | Schema name |
| HANA_TABLE | No | FINANCIAL_RATIOS | Table name |
| PORT | No | 8080 | Application port |
| DASH_DEBUG | No | false | Debug mode |

## Troubleshooting

### Connection Issues

**Problem:** Cannot connect to HANA database

**Solutions:**
- Verify HANA instance is running
- Check credentials in environment variables
- Ensure network connectivity to HANA Cloud
- Verify schema and table exist

### Deployment Issues

**Problem:** Application crashes on Cloud Foundry

**Solutions:**
```bash
# Check logs
cf logs financial-dashboard --recent

# Verify environment variables
cf env financial-dashboard

# Check app health
cf app financial-dashboard
```

### Empty Dashboard

**Problem:** Dashboard loads but shows no data

**Solutions:**
- Verify FINANCIAL_RATIOS table has data
- Check database connection in logs
- Ensure proper permissions on HANA schema

## Performance

- **Memory:** 1024MB recommended
- **Disk:** 1024MB minimum
- **Instances:** 1 (can scale horizontally)
- **Workers:** 4 Gunicorn workers
- **Timeout:** 120 seconds
- **Auto-refresh:** 5 minutes

## Security

- Never commit credentials to Git
- Use environment variables or Cloud Foundry services for secrets
- Enable HTTPS in production
- Regularly rotate database passwords
- Review Cloud Foundry security groups

## Development

### Running Tests

```bash
python -m py_compile app.py
python -m py_compile db/data_service.py
```

### Code Style

The project follows Python PEP 8 style guidelines.

## Support

For issues or questions:
1. Check the logs: `cf logs financial-dashboard --recent`
2. Review the troubleshooting section
3. Verify database connectivity
4. Check Cloud Foundry app status

## License

Proprietary - Internal Use Only
