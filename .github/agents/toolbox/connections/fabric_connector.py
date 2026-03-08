"""
Microsoft Fabric Lakehouse Connector
Connects to Fabric lakehouse tables using REST API or Spark
"""

from typing import List, Dict, Any
import requests
from azure.identity import DefaultAzureCredential, ClientSecretCredential


class FabricConnector:
    """Connect to Microsoft Fabric lakehouse and extract table metadata."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.token = None
        self.base_url = "https://api.fabric.microsoft.com/v1"
        
    def connect(self) -> bool:
        """Authenticate to Fabric using Azure credentials."""
        try:
            auth_type = self.config.get('authentication', 'default')
            
            if auth_type == 'service_principal':
                credential = ClientSecretCredential(
                    tenant_id=self.config['tenant_id'],
                    client_id=self.config['client_id'],
                    client_secret=self.config['client_secret']
                )
            else:
                credential = DefaultAzureCredential()
            
            # Get token for Fabric API
            self.token = credential.get_token("https://api.fabric.microsoft.com/.default").token
            return True
            
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False
    
    def get_metadata(self) -> List[Dict[str, Any]]:
        """Extract metadata for specified lakehouse tables or all tables if not specified."""
        if not self.token:
            raise Exception("Not authenticated to Fabric")
        
        tables_metadata = []
        workspace_id = self.config['workspace_id']
        lakehouse_name = self.config['lakehouse_name']
        tables = self.config.get('tables', None)
        
        # Get lakehouse ID from name
        lakehouse_id = self._get_lakehouse_id(workspace_id, lakehouse_name)
        
        if not lakehouse_id:
            raise Exception(f"Lakehouse '{lakehouse_name}' not found")
        
        # If no tables specified, discover all tables in lakehouse
        if tables is None or tables == [] or tables == ['*']:
            tables = self._discover_tables(workspace_id, lakehouse_id)
            print(f"  Auto-discovered {len(tables)} tables in lakehouse")
        
        for table in tables:
            metadata = self._get_table_metadata(workspace_id, lakehouse_id, table)
            tables_metadata.append(metadata)
        
        return tables_metadata
    
    def _discover_tables(self, workspace_id: str, lakehouse_id: str) -> List[str]:
        """Discover all tables in the lakehouse."""
        url = f"{self.base_url}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        tables_list = response.json().get('value', [])
        return [table['name'] for table in tables_list]
    
    def _get_lakehouse_id(self, workspace_id: str, lakehouse_name: str) -> str:
        """Get lakehouse ID from its name."""
        url = f"{self.base_url}/workspaces/{workspace_id}/lakehouses"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        lakehouses = response.json().get('value', [])
        for lh in lakehouses:
            if lh['displayName'] == lakehouse_name:
                return lh['id']
        
        return None
    
    def _get_table_metadata(self, workspace_id: str, lakehouse_id: str, table_name: str) -> Dict[str, Any]:
        """Get column metadata for a lakehouse table."""
        # Using Fabric API to get table schema
        url = f"{self.base_url}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables/{table_name}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        table_info = response.json()
        columns = []
        
        # Parse schema from table info
        for col in table_info.get('columns', []):
            col_name = col['name']
            data_type = self._map_spark_type(col['type'])
            
            columns.append({
                "name": col_name,
                "data_type": data_type,
                "description": f"Column from Fabric lakehouse table {table_name}"
            })
        
        return {
            "table_name": table_name,
            "source_type": "fabric_lakehouse",
            "workspace_id": workspace_id,
            "lakehouse_id": lakehouse_id,
            "columns": columns
        }
    
    def _map_spark_type(self, spark_type: str) -> str:
        """Map Spark/Delta Lake types to standard SQL types."""
        spark_type = spark_type.lower()
        
        type_map = {
            'integer': 'INT',
            'long': 'BIGINT',
            'short': 'SMALLINT',
            'byte': 'TINYINT',
            'double': 'FLOAT',
            'float': 'FLOAT',
            'decimal': 'DECIMAL(10,2)',
            'string': 'VARCHAR(255)',
            'date': 'DATE',
            'timestamp': 'DATETIME',
            'boolean': 'BOOLEAN',
            'binary': 'VARBINARY'
        }
        
        # Handle decimal with precision
        if 'decimal' in spark_type:
            return spark_type.upper().replace('DECIMAL', 'DECIMAL')
        
        return type_map.get(spark_type, 'VARCHAR(255)')


# Alternative: Using PySpark for Fabric
class FabricSparkConnector:
    """Alternative connector using PySpark for Fabric lakehouse access."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.spark = None
    
    def connect(self) -> bool:
        """Initialize Spark session (in Fabric notebook context)."""
        try:
            from pyspark.sql import SparkSession
            self.spark = SparkSession.builder.getOrCreate()
            return True
        except Exception as e:
            print(f"Spark initialization failed: {e}")
            return False
    
    def get_metadata(self) -> List[Dict[str, Any]]:
        """Extract metadata using Spark catalog."""
        tables_metadata = []
        lakehouse_name = self.config['lakehouse_name']
        tables = self.config.get('tables', [])
        
        for table in tables:
            df = self.spark.table(f"{lakehouse_name}.{table}")
            columns = []
            
            for field in df.schema.fields:
                columns.append({
                    "name": field.name,
                    "data_type": str(field.dataType),
                    "nullable": field.nullable,
                    "description": f"Column from {table}"
                })
            
            tables_metadata.append({
                "table_name": table,
                "source_type": "fabric_lakehouse_spark",
                "lakehouse": lakehouse_name,
                "columns": columns
            })
        
        return tables_metadata


# Example usage
if __name__ == "__main__":
    config = {
        "workspace_id": "your-workspace-guid",
        "lakehouse_name": "AnalyticsLakehouse",
        "authentication": "default",
        "tables": ["sales_raw", "customer_master"]
    }
    
    connector = FabricConnector(config)
    if connector.connect():
        metadata = connector.get_metadata()
        print(metadata)
