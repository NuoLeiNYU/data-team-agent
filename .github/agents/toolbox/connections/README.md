# Data Source Connection Toolbox

This directory contains connection handlers for various data sources that the **source-analyst** agent can use to extract metadata.

## Supported Connection Types

| Type | Handler | Description |
|------|---------|-------------|
| **SQL Database** | `sql_connector.py` | SQL Server, PostgreSQL, MySQL, Oracle |
| **Fabric Lakehouse** | `fabric_connector.py` | Microsoft Fabric lakehouse tables |
| **SharePoint** | `sharepoint_connector.py` | Excel files and SharePoint lists |
| **Local Files** | `file_connector.py` | CSV, Excel, Parquet, JSON |
| **Cloud Storage** | `cloud_connector.py` | Azure Blob, AWS S3, Google Cloud Storage |
| **REST API** | `api_connector.py` | REST APIs returning JSON/XML |

## Usage

### 1. Define Connection Configuration

Create a `connections.json` file with your data source details:

```json
{
  "sources": [
    {
      "name": "sales_db",
      "type": "sql",
      "config": {
        "connection_string": "Server=myserver;Database=SalesDB;...",
        "tables": ["orders", "order_items"]
      }
    },
    {
      "name": "customer_lakehouse",
      "type": "fabric",
      "config": {
        "workspace_id": "abc-123",
        "lakehouse_name": "CustomerData",
        "tables": ["dim_customers", "bridge_contacts"]
      }
    }
  ]
}
```

### 2. Invoke Source Analyst

The source-analyst agent will:
1. Read the `connections.json` configuration
2. Use appropriate connector for each source type
3. Extract metadata from all configured sources
4. Output consolidated JSON metadata

## Connection Security

- **Never commit credentials** to version control
- Use environment variables or Azure Key Vault for secrets
- Each connector supports multiple authentication methods
- See individual connector files for auth options

## Extending the Toolbox

To add a new connector:
1. Create `new_connector.py` in this directory
2. Implement `connect()` and `get_metadata()` methods
3. Add to the `CONNECTOR_MAP` in `connector_factory.py`
4. Update this README with documentation
