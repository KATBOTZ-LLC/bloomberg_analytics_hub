# CFO Pulse - Architecture Diagrams & Visual Documentation

This document contains all architecture diagrams in Mermaid format. Copy these into your Google Docs or use a Mermaid viewer.

---

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph "External Data Sources"
        A[Bloomberg API<br/>Financial Data]
        B[SAP S/4HANA<br/>ACDOCA - Phase 2]
    end
    
    subgraph "SAP BTP Cloud Foundry"
        subgraph "Data Ingestion Service"
            C[Bloomberg Connector<br/>OAuth2]
            D[Data Validator]
            E[Duplicate Detector]
            F[Email Notifier<br/>SendGrid]
        end
        
        subgraph "SAP HANA Cloud Database"
            G[(FINANCIAL_RATIOS)]
            H[(FINANCIAL_DATA_ADVANCED)]
            I[(INGESTION_LOGS)]
            J[(USERS)]
            K[(ACCESS_REQUESTS)]
        end
        
        subgraph "CFO Dashboard Service"
            L[Flask App]
            M[Authentication Service]
            N[Data Service Layer]
            O[Plotly Dash UI]
        end
    end
    
    subgraph "End Users"
        P[CFO / Finance Team<br/>Web Browser]
    end
    
    A -->|Daily 9 AM<br/>REST API| C
    B -.->|Phase 2<br/>OData/RFC| C
    C --> D
    D --> E
    E --> G
    E --> H
    C --> I
    E -->|Success/Fail<br/>Email| F
    
    P -->|HTTPS| L
    L --> M
    M --> J
    M --> K
    L --> N
    N --> G
    N --> H
    L --> O
    O -->|Render| P
    
    style A fill:#e1f5ff
    style B fill:#fff3cd
    style G fill:#d4edda
    style H fill:#d4edda
    style P fill:#f8d7da
```

---

## 2. Data Ingestion Flow (Detailed)

```mermaid
sequenceDiagram
    participant Scheduler as Cloud Foundry<br/>Task Scheduler
    participant Ingest as Ingestion Service
    participant Bloomberg as Bloomberg API
    participant Validator as Data Validator
    participant HANA as SAP HANA Cloud
    participant Email as SendGrid Email
    
    Scheduler->>Ingest: Trigger (9:00 AM Daily)
    Ingest->>Email: Send "Ingestion Started" email
    
    Ingest->>Bloomberg: OAuth2 Authentication
    Bloomberg-->>Ingest: Access Token
    
    Ingest->>Bloomberg: GET /financial-data<br/>(50 companies, basic metrics)
    Bloomberg-->>Ingest: JSON Response (DataFrame)
    
    Ingest->>Validator: Validate Data Quality
    Validator->>Validator: Check Empty Response
    Validator->>Validator: Check Null Values
    Validator->>Validator: Check Value Ranges
    Validator->>Validator: Bloomberg Error Codes (RC)
    Validator-->>Ingest: Validation Report
    
    alt Validation Warnings
        Ingest->>Email: Send "Data Quality Warning"
    end
    
    Ingest->>HANA: Query Existing Records
    HANA-->>Ingest: Existing Data
    
    Ingest->>Ingest: Detect Duplicates
    
    alt New Records Found
        Ingest->>HANA: INSERT INTO FINANCIAL_RATIOS
        HANA-->>Ingest: Records Inserted
    end
    
    Ingest->>HANA: INSERT INTO INGESTION_LOGS
    
    alt Success
        Ingest->>Email: Send "Success" Email<br/>(Fetched, Inserted, Skipped)
    else Failure
        Ingest->>Email: Send "Failure" Email<br/>(Error Details)
    end
    
    Ingest-->>Scheduler: Complete (Exit Code 0/1)
```

---

## 3. User Authentication Flow

```mermaid
sequenceDiagram
    participant User as User Browser
    participant LoginPage as Login Page
    participant FlaskApp as Flask Server
    participant AuthService as Auth Service
    participant HANA as HANA (USERS table)
    participant Crypto as AES Encryption
    participant Email as SendGrid
    
    User->>LoginPage: Enter Email + Password
    LoginPage->>FlaskApp: POST /login
    
    FlaskApp->>AuthService: authenticate(email, password)
    
    AuthService->>HANA: SELECT * FROM USERS<br/>WHERE EMAIL = ?
    HANA-->>AuthService: User Record (encrypted password)
    
    alt User Not Found
        AuthService-->>FlaskApp: None
        FlaskApp-->>User: 404 "User not found"
    else User Found
        AuthService->>Crypto: decrypt_password(encrypted)
        Crypto-->>AuthService: Plain Password
        
        AuthService->>AuthService: Compare Passwords
        
        alt Password Match
            AuthService->>HANA: UPDATE last_login, login_attempts=0
            AuthService-->>FlaskApp: User Object (id, email, role)
            FlaskApp->>FlaskApp: Create Session<br/>(24h timeout)
            FlaskApp-->>User: 200 Success + Redirect /dashboard/
        else Password Mismatch
            AuthService->>HANA: UPDATE login_attempts + 1
            AuthService->>Email: Send "Failed Login Alert"<br/>(IP, Timestamp)
            AuthService-->>FlaskApp: None
            FlaskApp-->>User: 401 "Invalid credentials"
        end
    end
```

---

## 4. Dashboard Data Loading Flow

```mermaid
sequenceDiagram
    participant User as User Browser
    participant Dash as Dash Frontend
    participant DataService as Data Service
    participant Cache as In-Memory Cache
    participant HANA as HANA Database
    
    User->>Dash: Load Dashboard Page
    Dash->>DataService: get_financial_ratios(limit=50)
    
    DataService->>Cache: Check Cache<br/>(Key: "financial_ratios_50")
    
    alt Cache Hit
        Cache-->>DataService: Cached DataFrame
        DataService-->>Dash: Return Data
    else Cache Miss
        DataService->>HANA: SELECT * FROM FINANCIAL_RATIOS<br/>ORDER BY INSERTED_AT DESC<br/>LIMIT 50
        HANA-->>DataService: 50 Latest Records
        
        DataService->>DataService: Convert to DataFrame<br/>Type Conversion
        
        DataService->>Cache: Store in Cache<br/>(TTL: 1 minute)
        DataService-->>Dash: Return DataFrame
    end
    
    Dash->>Dash: Create Plotly Charts<br/>(Bar, Line, Box, Heatmap)
    Dash-->>User: Render HTML + Charts
    
    Note over User,HANA: Auto-refresh every 5 minutes
    
    loop Every 5 minutes
        Dash->>DataService: get_financial_ratios(limit=50)
        DataService->>HANA: Fetch Latest Data
        HANA-->>DataService: Updated Records
        Dash->>Dash: Update Charts
        Dash-->>User: Re-render
    end
```

---

## 5. Company Comparison Feature Flow

```mermaid
flowchart TD
    A[User Selects Companies] -->|KatBotz, Salesforce, Oracle| B{Data Source?}
    
    B -->|KatBotz<br/>Demo Data| C[Load competitor_data.json]
    B -->|Real Clients<br/>Phase 2| D[Query CLIENT_FINANCIALS<br/>ACDOCA Data]
    B -->|Competitors| E[Query FINANCIAL_RATIOS<br/>Bloomberg Data]
    
    C --> F[Normalize Data Format]
    D --> F
    E --> F
    
    F --> G[Merge DataFrames]
    
    G --> H{Comparison Type?}
    
    H -->|Bar Chart| I[Create Side-by-Side Bars]
    H -->|Radar Chart| J[Create Spider Plot]
    H -->|Table| K[Create Comparison Table]
    
    I --> L[Apply Colors<br/>Green: Above Avg<br/>Red: Below Avg]
    J --> L
    K --> L
    
    L --> M[Render to User]
    
    M --> N{User Action?}
    
    N -->|Export| O[Generate Excel/PDF]
    N -->|Drill-Down| P[Show Detailed Metrics]
    N -->|Change Selection| A
    
    style C fill:#fff3cd
    style D fill:#d4edda
    style E fill:#e1f5ff
    style M fill:#f8d7da
```

---

## 6. Database Schema (Entity Relationship Diagram)

```mermaid
erDiagram
    USERS ||--o{ ACCESS_REQUESTS : "requests"
    USERS {
        int ID PK
        string EMAIL UK
        string PASSWORD_ENCRYPTED
        string FULL_NAME
        string ROLE
        boolean IS_ACTIVE
        timestamp CREATED_AT
        timestamp LAST_LOGIN
        int LOGIN_ATTEMPTS
    }
    
    ACCESS_REQUESTS {
        int ID PK
        string NAME
        string EMAIL UK
        string COMPANY
        clob REASON
        string STATUS
        timestamp REQUESTED_AT
        string REVIEWED_BY FK
        timestamp REVIEWED_AT
        clob ADMIN_NOTES
    }
    
    FINANCIAL_RATIOS {
        int ID PK
        date DATA_DATE
        string TICKER
        string IDENTIFIER_TYPE
        string IDENTIFIER_VALUE
        string ID_BB_GLOBAL
        decimal TOT_DEBT_TO_TOT_ASSET
        decimal CASH_DVD_COVERAGE
        decimal TOT_DEBT_TO_EBITDA
        decimal CUR_RATIO
        decimal QUICK_RATIO
        decimal GROSS_MARGIN
        decimal INTEREST_COVERAGE_RATIO
        decimal EBITDA_MARGIN
        decimal TOT_LIAB_AND_EQY
        decimal NET_DEBT_TO_SHRHLDR_EQTY
        timestamp INSERTED_AT
    }
    
    FINANCIAL_DATA_ADVANCED {
        int ID PK
        string TICKER
        string IDENTIFIER_TYPE
        string IDENTIFIER_VALUE
        decimal IS_NET_INCOME
        decimal IS_REVENUE
        decimal IS_COGS
        decimal IS_OPERATING_EXPN
        decimal EBIT
        decimal EBITDA
        decimal EQY_DPS
        timestamp INSERTED_AT
    }
    
    INGESTION_LOGS {
        string RUN_ID PK
        timestamp START_TIME
        timestamp END_TIME
        string STATUS
        int RECORDS_FETCHED
        int RECORDS_INSERTED
        int RECORDS_FAILED
        int RECORDS_SKIPPED
        int NEW_ENTRIES
        int TOTAL_RECORDS
        clob ERROR_MESSAGE
        string TRIGGERED_BY
        string DATA_SOURCE
    }
    
    CLIENT_CONNECTIONS {
        string CLIENT_ID PK
        string CLIENT_NAME
        string SAP_HOST
        string SAP_CLIENT
        string CONNECTION_TYPE
        string AUTH_METHOD
        string CREDENTIALS_ENCRYPTED
        string STATUS
        timestamp LAST_SYNC
        timestamp CREATED_AT
    }
    
    GL_ACCOUNT_MAPPINGS {
        int MAPPING_ID PK
        string CLIENT_ID FK
        string GL_ACCOUNT
        string GL_DESCRIPTION
        string METRIC_CATEGORY
        string METRIC_NAME
        string ACCOUNT_TYPE
        boolean IS_DEBIT
        decimal MULTIPLIER
    }
    
    CLIENT_FINANCIALS {
        int RECORD_ID PK
        string CLIENT_ID FK
        date DATA_DATE
        int FISCAL_YEAR
        int FISCAL_PERIOD
        decimal CUR_RATIO
        decimal QUICK_RATIO
        decimal GROSS_MARGIN
        decimal EBITDA_MARGIN
        timestamp EXTRACTED_AT
    }
    
    CLIENT_CONNECTIONS ||--o{ GL_ACCOUNT_MAPPINGS : "has"
    CLIENT_CONNECTIONS ||--o{ CLIENT_FINANCIALS : "generates"
```

---

## 7. Phase 2: ACDOCA Integration Architecture

```mermaid
graph TB
    subgraph "Client SAP S/4HANA System"
        A1[ACDOCA Table<br/>Universal Journal]
        A2[Chart of Accounts<br/>SKA1]
        A3[OData Service<br/>Gateway]
        A4[RFC Function Module<br/>ZFIN_GET_ACDOCA]
    end
    
    subgraph "Network Security"
        B1[Firewall]
        B2[OAuth2 Auth Server]
        B3[mTLS Certificate]
    end
    
    subgraph "CFO Pulse - ACDOCA Integration Service"
        C1[Connection Manager]
        C2[ACDOCA Extractor<br/>OData/RFC]
        C3[G/L Account Mapper]
        C4[Financial Calculator]
        C5[Data Validator]
        C6[Sync Scheduler]
    end
    
    subgraph "SAP HANA Cloud"
        D1[(CLIENT_CONNECTIONS)]
        D2[(GL_ACCOUNT_MAPPINGS)]
        D3[(CLIENT_FINANCIALS)]
        D4[(SYNC_LOGS)]
    end
    
    subgraph "CFO Dashboard"
        E1[Enhanced Comparison View]
        E2[Variance Analysis]
        E3[Drill-Down Explorer]
    end
    
    A1 --> A3
    A1 -.-> A4
    A2 --> C3
    
    A3 -->|HTTPS| B1
    A4 -.->|RFC| B1
    B1 --> B2
    B2 -->|Token| C1
    B3 -.->|Cert Auth| C1
    
    C1 --> C2
    C2 -->|Extract| A3
    C2 -.->|Extract| A4
    
    C2 --> C3
    C3 --> C4
    C4 --> C5
    
    D2 -->|Mappings| C3
    D1 -->|Config| C1
    
    C5 --> D3
    C6 --> D4
    C6 -->|Schedule| C2
    
    D3 --> E1
    D3 --> E2
    D3 --> E3
    
    style A1 fill:#fff3cd
    style A3 fill:#fff3cd
    style C2 fill:#d4edda
    style C4 fill:#d4edda
    style D3 fill:#e1f5ff
    style E1 fill:#f8d7da
```

---

## 8. ACDOCA Data Extraction & Transformation Flow

```mermaid
sequenceDiagram
    participant Scheduler as Daily Scheduler<br/>6:00 AM
    participant Connector as ACDOCA Connector
    participant SAP as SAP S/4HANA<br/>OData Service
    participant Mapper as G/L Mapper
    participant Calculator as Ratio Calculator
    participant HANA as HANA Database
    participant Email as Email Notifier
    
    Scheduler->>Connector: Trigger Sync for Client XYZ
    
    Connector->>HANA: Load Connection Config
    HANA-->>Connector: SAP Host, Client, Auth
    
    Connector->>SAP: POST /oauth2/token
    SAP-->>Connector: Access Token (Valid 1h)
    
    Connector->>SAP: GET /ACDOCA?$filter=RBUKRS eq '1000'<br/>AND GJAHR eq '2026'
    SAP-->>Connector: ACDOCA Records (10,000 rows)
    
    Connector->>Connector: Convert JSON to DataFrame
    
    Connector->>Mapper: Map G/L Accounts
    Mapper->>HANA: Load GL_ACCOUNT_MAPPINGS
    HANA-->>Mapper: Mapping Rules
    
    Mapper->>Mapper: Group by Category:<br/>- Revenue: [400000-499999]<br/>- COGS: [500000-599999]<br/>- OpEx: [600000-699999]
    
    Mapper-->>Calculator: Categorized Data
    
    Calculator->>Calculator: Calculate Current Ratio:<br/>SUM(Current Assets) / SUM(Current Liabilities)
    
    Calculator->>Calculator: Calculate Gross Margin:<br/>(Revenue - COGS) / Revenue × 100
    
    Calculator->>Calculator: Calculate EBITDA Margin:<br/>(EBITDA) / Revenue × 100
    
    Calculator->>Calculator: Calculate Debt-to-Asset:<br/>Total Debt / Total Assets
    
    Calculator->>Calculator: Validate Results:<br/>- Check Balance Sheet Equation<br/>- Verify Ratio Ranges
    
    alt Validation Passed
        Calculator->>HANA: INSERT INTO CLIENT_FINANCIALS
        HANA-->>Calculator: Success
        Calculator->>Email: Send "Sync Success" Email
    else Validation Failed
        Calculator->>Email: Send "Data Quality Issue" Email
    end
    
    Calculator->>HANA: Log Sync Metadata
```

---

## 9. User Access Management Workflow (Phase 1 Completion)

```mermaid
stateDiagram-v2
    [*] --> RequestSubmitted: User fills access form
    
    RequestSubmitted --> PendingReview: Email sent to admin
    
    PendingReview --> Approved: Admin approves
    PendingReview --> Rejected: Admin rejects
    
    Approved --> UserCreated: Create user in USERS table
    UserCreated --> PasswordGenerated: Generate temp password
    PasswordGenerated --> WelcomeEmailSent: Send credentials email
    WelcomeEmailSent --> Active: User can login
    
    Rejected --> RejectionEmailSent: Send rejection email
    RejectionEmailSent --> [*]
    
    Active --> Deactivated: Admin deactivates
    Deactivated --> SessionInvalidated: Clear all sessions
    SessionInvalidated --> DeactivationEmailSent: Notify user
    DeactivationEmailSent --> Inactive
    
    Inactive --> Reactivated: Admin reactivates
    Reactivated --> ReactivationEmailSent: Notify user
    ReactivationEmailSent --> Active
    
    note right of PendingReview
        Admin sees pending request
        in /admin dashboard
    end note
    
    note right of Active
        User has 24-hour
        session timeout
    end note
```

---

## 10. ML Forecasting Architecture (Phase 1 Completion)

```mermaid
graph LR
    subgraph "Data Sources"
        A[FINANCIAL_RATIOS<br/>Historical Data]
        B[CLIENT_FINANCIALS<br/>Client Data]
    end
    
    subgraph "ML Pipeline"
        C[Data Preprocessor]
        D[Feature Engineering]
        E[Prophet Model<br/>Time Series]
        F[Anomaly Detector<br/>Statistical]
        G[Trend Classifier<br/>Linear Regression]
    end
    
    subgraph "Predictions & Insights"
        H[Forecast<br/>Next 4 Quarters]
        I[Anomaly Alerts<br/>Unusual Patterns]
        J[Trend Direction<br/>Improving/Declining]
    end
    
    subgraph "Dashboard Display"
        K[Forecast Chart<br/>with Confidence Bands]
        L[Anomaly Markers<br/>Red Dots]
        M[Trend Badges<br/>🟢🟡🔴]
    end
    
    A --> C
    B --> C
    C --> D
    
    D --> E
    D --> F
    D --> G
    
    E --> H
    F --> I
    G --> J
    
    H --> K
    I --> L
    J --> M
    
    style E fill:#d4edda
    style F fill:#fff3cd
    style G fill:#e1f5ff
    style K fill:#f8d7da
```

---

## 11. Deployment Architecture (Cloud Foundry)

```mermaid
graph TB
    subgraph "SAP BTP Cloud Foundry"
        subgraph "Application Layer"
            A1[bloomberg-ingestion<br/>Python App]
            A2[financial-dashboard<br/>Dash App]
        end
        
        subgraph "Service Layer"
            B1[HANA Cloud Service<br/>Database Instance]
            B2[Application Logging Service]
            B3[Autoscaler Service]
        end
        
        subgraph "Route Layer"
            C1[Cloud Foundry Router<br/>Load Balancer]
        end
    end
    
    subgraph "External Services"
        D1[Bloomberg API]
        D2[SendGrid Email API]
        D3[SAP S/4HANA<br/>Client Systems]
    end
    
    subgraph "Scheduled Tasks"
        E1[Daily Ingestion Job<br/>9:00 AM]
        E2[ACDOCA Sync Job<br/>6:00 AM - Phase 2]
    end
    
    subgraph "Monitoring"
        F1[Cloud Foundry Logs]
        F2[HANA Cockpit]
        F3[Application Metrics]
    end
    
    Internet((Internet<br/>HTTPS)) --> C1
    C1 --> A1
    C1 --> A2
    
    A1 --> B1
    A2 --> B1
    A1 --> B2
    A2 --> B2
    
    B3 --> A2
    
    E1 --> A1
    E2 -.-> A1
    
    A1 --> D1
    A1 --> D2
    A1 -.-> D3
    
    A1 --> F1
    A2 --> F1
    B1 --> F2
    A1 --> F3
    A2 --> F3
    
    style A1 fill:#d4edda
    style A2 fill:#e1f5ff
    style B1 fill:#fff3cd
    style E1 fill:#f8d7da
```

---

## 12. Security Architecture

```mermaid
graph TB
    subgraph "User Access Layer"
        A1[User Browser]
        A2[Corporate VPN<br/>Optional]
    end
    
    subgraph "Application Security"
        B1[HTTPS/TLS 1.3<br/>Encryption]
        B2[OAuth2 Authentication<br/>Bloomberg]
        B3[Session Management<br/>24h Timeout]
        B4[RBAC<br/>Role-Based Access]
    end
    
    subgraph "Data Security"
        C1[Password Encryption<br/>AES-256]
        C2[Data Encryption at Rest<br/>HANA Native]
        C3[Encrypted Backups<br/>Daily]
    end
    
    subgraph "Network Security"
        D1[Firewall Rules<br/>IP Whitelisting]
        D2[DDoS Protection<br/>Cloud Foundry]
        D3[mTLS for RFC<br/>Phase 2]
    end
    
    subgraph "Compliance & Audit"
        E1[Audit Logs<br/>All Data Access]
        E2[Login Tracking<br/>IP + Timestamp]
        E3[Failed Login Alerts<br/>Email]
        E4[GDPR Compliance<br/>Data Deletion]
    end
    
    A1 --> A2
    A2 --> B1
    A1 --> B1
    
    B1 --> B2
    B1 --> B3
    B3 --> B4
    
    B4 --> C1
    C1 --> C2
    C2 --> C3
    
    B1 --> D1
    D1 --> D2
    D2 -.-> D3
    
    B3 --> E1
    B3 --> E2
    E2 --> E3
    C2 --> E4
    
    style B1 fill:#d4edda
    style C1 fill:#fff3cd
    style E1 fill:#f8d7da
```

---

## 13. Data Quality & Validation Pipeline

```mermaid
flowchart TD
    A[Bloomberg API Response] --> B{Empty Data?}
    B -->|Yes| Z[❌ FAIL<br/>Send Alert]
    B -->|No| C{Bloomberg Errors<br/>RC != 0?}
    
    C -->|Yes| D[Filter Error Rows]
    D --> E{Any Valid Rows?}
    E -->|No| Z
    E -->|Yes| F{Missing Values<br/>>30%?}
    
    C -->|No| F
    
    F -->|Yes| G[Segregate Incomplete Rows]
    G --> H[Email Warning<br/>with Details]
    H --> I{Sufficient Data<br/>>70% complete?}
    I -->|No| Z
    I -->|Yes| J[Check Value Ranges]
    
    F -->|No| J
    
    J --> K{Current Ratio<br/>0-100?}
    K -->|No| L[Flag Anomaly]
    K -->|Yes| M{Quick Ratio<br/>0-100?}
    
    M -->|No| L
    M -->|Yes| N{Gross Margin<br/>-100 to 200?}
    
    N -->|No| L
    N -->|Yes| O{EBITDA Margin<br/>-200 to 200?}
    
    O -->|No| L
    O -->|Yes| P[Duplicate Detection]
    
    L --> P
    
    P --> Q{Exact Match<br/>in HANA?}
    Q -->|Yes| R[Skip Duplicate<br/>Log Skipped Count]
    Q -->|No| S[✅ VALID<br/>Ready for Insert]
    
    S --> T[INSERT INTO<br/>FINANCIAL_RATIOS]
    T --> U[Log Success Metrics]
    R --> U
    
    U --> V[Send Success Email]
    
    style Z fill:#f8d7da
    style S fill:#d4edda
    style V fill:#d4edda
    style L fill:#fff3cd
```

---

## 14. Performance Optimization Architecture

```mermaid
graph TB
    subgraph "Frontend Optimization"
        A1[React Memoization]
        A2[Lazy Loading Charts]
        A3[Client-Side Caching<br/>localStorage]
        A4[Code Splitting]
    end
    
    subgraph "Backend Optimization"
        B1[In-Memory Cache<br/>1-min TTL]
        B2[Database Connection Pool]
        B3[Query Optimization]
        B4[Async Processing]
    end
    
    subgraph "Database Optimization"
        C1[Indexes on TICKER, DATE]
        C2[Materialized Views]
        C3[Column Store<br/>HANA Optimization]
        C4[Partition by Year]
    end
    
    subgraph "CDN & Network"
        D1[Static Asset CDN]
        D2[gzip Compression]
        D3[HTTP/2]
        D4[Keep-Alive Connections]
    end
    
    User[User Request] --> A1
    A1 --> A2
    A2 --> A3
    A3 --> B1
    
    B1 -->|Cache Miss| B2
    B2 --> B3
    B3 --> C1
    
    C1 --> C2
    C2 --> C3
    C3 --> C4
    
    C4 --> B4
    B4 --> D1
    D1 --> D2
    D2 --> D3
    D3 --> D4
    D4 --> Response[Fast Response<br/><500ms]
    
    style B1 fill:#d4edda
    style C1 fill:#fff3cd
    style Response fill:#e1f5ff
```

---

## How to Use These Diagrams

### Option 1: Render in Markdown Viewers
- **GitHub/GitLab**: Paste into .md files - diagrams render automatically
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **Online**: Use https://mermaid.live/ to preview and edit

### Option 2: Google Docs
1. Install "Mermaid Diagram Viewer" add-on for Google Docs
2. Or convert to images:
   - Go to https://mermaid.ink/
   - Paste Mermaid code
   - Download as PNG/SVG
   - Insert into Google Docs

### Option 3: Export as Images
```bash
# Using Mermaid CLI
npm install -g @mermaid-js/mermaid-cli
mmdc -i diagram.mmd -o diagram.png
```

---

**All diagrams are scalable, editable, and version-controlled!**
