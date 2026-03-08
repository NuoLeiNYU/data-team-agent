"""
SQL Server Database Connector
Connects to Microsoft SQL Server using Windows Authentication by default
"""

import pyodbc
import pandas as pd
from typing import List, Dict, Any


class SQLConnector:
    """Connect to SQL databases and extract table metadata."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connection = None
        
    def connect(self) -> bool:
        """Establish database connection."""
        try:
            # Build connection string based on config
            if 'connection_string' in self.config:
                conn_str = self.config['connection_string']
            else:
                conn_str = self._build_connection_string()
            
            self.connection = pyodbc.connect(conn_str)
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def _build_connection_string(self) -> str:
        """Build connection string from config components."""
        driver = self.config.get('driver', 'ODBC Driver 17 for SQL Server')
        server = self.config['server']
        database = self.config['database']
        auth = self.config.get('authentication', 'windows')
        
        if auth == 'sql':
            uid = self.config.get('username', '')
            pwd = self.config.get('password', '')
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd}"
        elif auth == 'ActiveDirectoryInteractive':
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Authentication=ActiveDirectoryInteractive"
        else:
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes"
    
    def get_metadata(self) -> List[Dict[str, Any]]:
        """Extract metadata for specified tables or all tables if not specified."""
        if not self.connection:
            raise Exception("Not connected to database")
        
        tables_metadata = []
        tables = self.config.get('tables', None)
        
        # If no tables specified, discover all user tables
        if tables is None or tables == [] or tables == ['*']:
            tables = self._discover_tables()
            print(f"  Auto-discovered {len(tables)} tables in database")
        
        for table in tables:
            metadata = self._get_table_metadata(table)
            tables_metadata.append(metadata)
        
        return tables_metadata
    
    def _discover_tables(self) -> List[str]:
        """Discover all user tables in the database."""
        cursor = self.connection.cursor()
        
        # Query to get all user tables (excluding system tables)
        query = """
        SELECT TABLE_SCHEMA + '.' + TABLE_NAME as FULL_TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
        ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        
        cursor.execute(query)
        tables = [row.FULL_TABLE_NAME for row in cursor.fetchall()]
        cursor.close()
        
        return tables
    
    def _get_table_metadata(self, table_name: str) -> Dict[str, Any]:
        """Get column metadata for a single table."""
        cursor = self.connection.cursor()
        
        # Parse schema and table name
        if '.' in table_name:
            schema, table = table_name.split('.', 1)
        else:
            schema = 'dbo'
            table = table_name
        
        # Query for column information
        query = """
        SELECT 
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.NUMERIC_PRECISION,
            c.NUMERIC_SCALE,
            c.IS_NULLABLE,
            pk.CONSTRAINT_TYPE as IS_PRIMARY_KEY
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN (
            SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME, tc.CONSTRAINT_TYPE
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
            JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc 
                ON ku.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        ) pk ON c.TABLE_SCHEMA = pk.TABLE_SCHEMA 
            AND c.TABLE_NAME = pk.TABLE_NAME 
            AND c.COLUMN_NAME = pk.COLUMN_NAME
        WHERE c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?
        ORDER BY c.ORDINAL_POSITION
        """
        
        cursor.execute(query, (schema, table))
        columns = []
        
        for row in cursor.fetchall():
            col_name = row.COLUMN_NAME
            data_type = self._map_sql_type(row.DATA_TYPE, row.CHARACTER_MAXIMUM_LENGTH, 
                                          row.NUMERIC_PRECISION, row.NUMERIC_SCALE)
            is_pk = row.IS_PRIMARY_KEY == 'PRIMARY KEY'
            
            columns.append({
                "name": col_name,
                "data_type": data_type,
                "nullable": row.IS_NULLABLE == 'YES',
                "is_primary_key": is_pk,
                "description": f"Column from {table_name}"
            })
        
        cursor.close()
        
        return {
            "table_name": table_name,
            "source_type": "sql_database",
            "database": self.config['database'],
            "columns": columns
        }
    
    def _map_sql_type(self, sql_type: str, max_length: int, precision: int, scale: int) -> str:
        """Map SQL Server types to standard types."""
        sql_type = sql_type.lower()
        
        if sql_type in ['int', 'bigint', 'smallint', 'tinyint']:
            return 'INT'
        elif sql_type in ['decimal', 'numeric', 'money', 'smallmoney']:
            return f'DECIMAL({precision},{scale})' if precision else 'DECIMAL(10,2)'
        elif sql_type in ['varchar', 'nvarchar', 'char', 'nchar']:
            return f'VARCHAR({max_length})' if max_length and max_length > 0 else 'VARCHAR(255)'
        elif sql_type == 'text':
            return 'TEXT'
        elif sql_type in ['datetime', 'datetime2', 'date', 'smalldatetime']:
            return 'DATETIME' if 'time' in sql_type else 'DATE'
        elif sql_type == 'bit':
            return 'BOOLEAN'
        elif sql_type in ['float', 'real']:
            return 'FLOAT'
        else:
            return sql_type.upper()
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()


# Example usage
if __name__ == "__main__":
    config = {
        "server": "localhost",
        "database": "SalesDB",
        "authentication": "windows",
        "tables": ["dbo.orders", "dbo.customers"]
    }
    
    connector = SQLConnector(config)
    if connector.connect():
        metadata = connector.get_metadata()
        print(metadata)
        connector.close()
