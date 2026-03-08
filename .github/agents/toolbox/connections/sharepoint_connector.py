"""
SharePoint Connector
Supports: Excel files, SharePoint Lists, CSV files in document libraries
"""

from typing import List, Dict, Any
import pandas as pd
from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.user_credential import UserCredential


class SharePointConnector:
    """Connect to SharePoint and extract data from files and lists."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ctx = None
        
    def connect(self) -> bool:
        """Authenticate to SharePoint."""
        try:
            site_url = self.config['site_url']
            auth_type = self.config.get('authentication', 'interactive')
            
            if auth_type == 'credentials':
                username = self.config['username']
                password = self.config['password']
                credentials = UserCredential(username, password)
                self.ctx = ClientContext(site_url).with_credentials(credentials)
            else:
                # Interactive authentication
                from office365.runtime.auth.authentication_context import AuthenticationContext
                auth_ctx = AuthenticationContext(site_url)
                auth_ctx.acquire_token_for_user()
                self.ctx = ClientContext(site_url, auth_ctx)
            
            return True
            
        except Exception as e:
            print(f"SharePoint authentication failed: {e}")
            return False
    
    def get_metadata(self) -> List[Dict[str, Any]]:
        """Extract metadata from SharePoint files and lists."""
        if not self.ctx:
            raise Exception("Not connected to SharePoint")
        
        tables_metadata = []
        
        # Process Excel/CSV files
        if 'files' in self.config:
            for file_name in self.config['files']:
                metadata = self._get_file_metadata(file_name)
                tables_metadata.extend(metadata)
        
        # Process SharePoint Lists
        if 'lists' in self.config:
            for list_name in self.config['lists']:
                metadata = self._get_list_metadata(list_name)
                tables_metadata.append(metadata)
        
        return tables_metadata
    
    def _get_file_metadata(self, file_name: str) -> List[Dict[str, Any]]:
        """Get metadata from Excel or CSV file in SharePoint."""
        library = self.config.get('library', 'Shared Documents')
        file_url = f"/{library}/{file_name}"
        
        # Download file to memory
        file_content = self._download_file(file_url)
        
        # Determine file type and parse
        if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            # Excel file - may have multiple sheets
            excel_file = pd.ExcelFile(file_content)
            metadata_list = []
            
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(file_content, sheet_name=sheet_name, nrows=0)
                metadata = self._dataframe_to_metadata(df, f"{file_name}_{sheet_name}")
                metadata_list.append(metadata)
            
            return metadata_list
            
        elif file_name.endswith('.csv'):
            df = pd.read_csv(file_content, nrows=0)
            return [self._dataframe_to_metadata(df, file_name)]
        
        return []
    
    def _get_list_metadata(self, list_name: str) -> Dict[str, Any]:
        """Get metadata from SharePoint List."""
        sp_list = self.ctx.web.lists.get_by_title(list_name)
        fields = sp_list.fields.get().execute_query()
        
        columns = []
        for field in fields:
            # Skip system fields
            if field.properties.get('Hidden', False):
                continue
            
            col_name = field.properties['InternalName']
            field_type = field.properties['TypeAsString']
            data_type = self._map_sharepoint_type(field_type)
            
            columns.append({
                "name": col_name,
                "data_type": data_type,
                "description": field.properties.get('Description', f"Field from {list_name}")
            })
        
        return {
            "table_name": list_name,
            "source_type": "sharepoint_list",
            "site_url": self.config['site_url'],
            "columns": columns
        }
    
    def _download_file(self, file_url: str) -> bytes:
        """Download file from SharePoint."""
        file = self.ctx.web.get_file_by_server_relative_url(file_url)
        content = file.download().execute_query()
        return content.content
    
    def _dataframe_to_metadata(self, df: pd.DataFrame, source_name: str) -> Dict[str, Any]:
        """Convert DataFrame structure to metadata format."""
        columns = []
        
        for col_name in df.columns:
            dtype = df[col_name].dtype
            data_type = self._map_pandas_type(dtype)
            
            columns.append({
                "name": col_name,
                "data_type": data_type,
                "description": f"Column from {source_name}"
            })
        
        return {
            "table_name": source_name.replace('.xlsx', '').replace('.csv', ''),
            "source_type": "sharepoint_file",
            "file_name": source_name,
            "columns": columns
        }
    
    def _map_sharepoint_type(self, sp_type: str) -> str:
        """Map SharePoint field types to SQL types."""
        type_map = {
            'Text': 'VARCHAR(255)',
            'Note': 'TEXT',
            'Number': 'DECIMAL(10,2)',
            'Integer': 'INT',
            'DateTime': 'DATETIME',
            'Boolean': 'BOOLEAN',
            'Choice': 'VARCHAR(100)',
            'Lookup': 'INT',
            'User': 'VARCHAR(255)',
            'Currency': 'DECIMAL(10,2)',
            'URL': 'VARCHAR(500)'
        }
        return type_map.get(sp_type, 'VARCHAR(255)')
    
    def _map_pandas_type(self, dtype) -> str:
        """Map pandas dtypes to SQL types."""
        dtype_str = str(dtype)
        
        if 'int' in dtype_str:
            return 'INT'
        elif 'float' in dtype_str:
            return 'DECIMAL(10,2)'
        elif 'datetime' in dtype_str:
            return 'DATETIME'
        elif 'bool' in dtype_str:
            return 'BOOLEAN'
        else:
            return 'VARCHAR(255)'


# Example usage
if __name__ == "__main__":
    config = {
        "site_url": "https://yourcompany.sharepoint.com/sites/DataTeam",
        "library": "Shared Documents",
        "files": ["Monthly Sales.xlsx", "Customer Export.csv"],
        "lists": ["Product Catalog"],
        "authentication": "interactive"
    }
    
    connector = SharePointConnector(config)
    if connector.connect():
        metadata = connector.get_metadata()
        print(metadata)
