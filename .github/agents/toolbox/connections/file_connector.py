"""
Local File Connector
Supports: CSV, Excel, Parquet, JSON files
"""

from typing import List, Dict, Any
import pandas as pd
import os
from pathlib import Path


class FileConnector:
    """Connect to local files and extract metadata."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
    def connect(self) -> bool:
        """Validate file paths exist."""
        base_path = self.config.get('base_path', '.')
        if not os.path.exists(base_path):
            print(f"Base path does not exist: {base_path}")
            return False
        return True
    
    def get_metadata(self) -> List[Dict[str, Any]]:
        """Extract metadata from local files."""
        tables_metadata = []
        base_path = Path(self.config.get('base_path', '.'))
        patterns = self.config.get('patterns', ['*.csv'])
        recursive = self.config.get('recursive', False)
        
        # Find all matching files
        files = []
        for pattern in patterns:
            if recursive:
                files.extend(base_path.rglob(pattern))
            else:
                files.extend(base_path.glob(pattern))
        
        # Process each file
        for file_path in files:
            try:
                metadata = self._get_file_metadata(file_path)
                if metadata:
                    tables_metadata.append(metadata)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
        
        return tables_metadata
    
    def _get_file_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Get metadata from a single file."""
        file_ext = file_path.suffix.lower()
        
        # Read file based on extension
        if file_ext == '.csv':
            df = pd.read_csv(file_path, nrows=100)  # Sample first 100 rows
        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, nrows=100)
        elif file_ext == '.parquet':
            df = pd.read_parquet(file_path)
            df = df.head(100)  # Limit to first 100 rows
        elif file_ext == '.json':
            df = pd.read_json(file_path)
            df = df.head(100)
        else:
            return None
        
        # Extract column metadata
        columns = []
        for col_name in df.columns:
            data_type = self._infer_type(df[col_name])
            sample_values = df[col_name].dropna().head(3).tolist()
            
            columns.append({
                "name": col_name,
                "data_type": data_type,
                "nullable": df[col_name].isnull().any(),
                "sample_values": [str(v) for v in sample_values],
                "description": f"Column from {file_path.name}"
            })
        
        return {
            "table_name": file_path.stem,  # Filename without extension
            "source_type": "local_file",
            "file_path": str(file_path),
            "file_format": file_ext[1:],  # Remove the dot
            "row_count": len(df),
            "columns": columns
        }
    
    def _infer_type(self, series: pd.Series) -> str:
        """Infer SQL data type from pandas Series."""
        dtype = series.dtype
        
        # Check for datetime
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return 'DATETIME'
        
        # Check for numeric types
        if pd.api.types.is_integer_dtype(dtype):
            return 'INT'
        
        if pd.api.types.is_float_dtype(dtype):
            # Check if it could be decimal (has actual decimal values)
            if series.dropna().apply(lambda x: x % 1 != 0).any():
                return 'DECIMAL(10,2)'
            return 'INT'
        
        # Check for boolean
        if pd.api.types.is_bool_dtype(dtype):
            return 'BOOLEAN'
        
        # For object/string types, infer based on content
        if dtype == 'object':
            # Try to detect date strings
            sample = series.dropna().head(10)
            if len(sample) > 0:
                try:
                    pd.to_datetime(sample)
                    return 'DATE'
                except:
                    pass
            
            # Check max length for VARCHAR
            max_len = series.astype(str).str.len().max()
            if pd.isna(max_len):
                max_len = 255
            else:
                max_len = min(int(max_len * 1.5), 8000)  # Add 50% buffer, cap at 8000
            
            return f'VARCHAR({max_len})'
        
        return 'VARCHAR(255)'


# Example usage
if __name__ == "__main__":
    config = {
        "base_path": "./data/sources",
        "patterns": ["*.csv", "*.xlsx"],
        "recursive": False
    }
    
    connector = FileConnector(config)
    if connector.connect():
        metadata = connector.get_metadata()
        for table in metadata:
            print(f"\nTable: {table['table_name']}")
            print(f"Columns: {len(table['columns'])}")
