"""
Connector Factory
Dynamically loads the appropriate connector based on source type
"""

from typing import Dict, Any, List
import json
from pathlib import Path


class ConnectorFactory:
    """Factory to create and manage data source connectors."""
    
    CONNECTOR_MAP = {
        'sql': 'sql_connector.SQLConnector',
        'fabric': 'fabric_connector.FabricConnector',
        'sharepoint': 'sharepoint_connector.SharePointConnector',
        'file': 'file_connector.FileConnector',
        'cloud': 'cloud_connector.CloudConnector',
        'api': 'api_connector.APIConnector'
    }
    
    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """Load connections configuration from JSON file."""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def create_connector(source_type: str, config: Dict[str, Any]):
        """Create a connector instance based on source type."""
        if source_type not in ConnectorFactory.CONNECTOR_MAP:
            raise ValueError(f"Unknown source type: {source_type}")
        
        module_class = ConnectorFactory.CONNECTOR_MAP[source_type]
        module_name, class_name = module_class.rsplit('.', 1)
        
        # Dynamic import
        module = __import__(module_name, fromlist=[class_name])
        connector_class = getattr(module, class_name)
        
        return connector_class(config)
    
    @staticmethod
    def extract_all_metadata(config_path: str) -> List[Dict[str, Any]]:
        """
        Main orchestration function:
        1. Load connections.json
        2. Create appropriate connector for each source
        3. Extract metadata from all sources
        4. Return consolidated metadata
        """
        config = ConnectorFactory.load_config(config_path)
        all_metadata = []
        
        for source in config.get('sources', []):
            # Skip disabled sources
            if not source.get('enabled', True):
                print(f"Skipping disabled source: {source['name']}")
                continue
            
            source_name = source['name']
            source_type = source['type']
            source_config = source['config']
            
            print(f"Processing source: {source_name} (type: {source_type})")
            
            try:
                # Create connector
                connector = ConnectorFactory.create_connector(source_type, source_config)
                
                # Connect
                if connector.connect():
                    # Extract metadata
                    metadata = connector.get_metadata()
                    
                    # Add source context
                    for table_meta in metadata:
                        table_meta['source_name'] = source_name
                    
                    all_metadata.extend(metadata)
                    print(f"  ✓ Extracted {len(metadata)} tables")
                else:
                    print(f"  ✗ Failed to connect to {source_name}")
                
                # Cleanup
                if hasattr(connector, 'close'):
                    connector.close()
                    
            except Exception as e:
                print(f"  ✗ Error processing {source_name}: {e}")
        
        return all_metadata
    
    @staticmethod
    def save_metadata(metadata: List[Dict[str, Any]], output_path: str):
        """Save extracted metadata to JSON file."""
        output = {"tables": metadata}
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Metadata saved to {output_path}")


# Command-line interface
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python connector_factory.py <connections.json> [output.json]")
        sys.exit(1)
    
    config_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "metadata_output.json"
    
    print("=" * 60)
    print("Data Source Metadata Extraction")
    print("=" * 60)
    
    # Extract metadata from all sources
    metadata = ConnectorFactory.extract_all_metadata(config_path)
    
    # Save results
    ConnectorFactory.save_metadata(metadata, output_path)
    
    print(f"\n✓ Complete! Processed {len(metadata)} tables from multiple sources")
