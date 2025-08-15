import os
from typing import List, Dict, Any
from test.lang_definitions.base_test_definition import BaseTestDefinition

class JavascriptTestDefinition(BaseTestDefinition):
    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def supported_relationships(self) -> List[str]:
        return [
            'calls',
            # 'imports', # not implemented yet
            'inherits',
            'instantiates',
            'contains_method',
            # 'references_variable', # not implemented yet
        ]

    def get_sample_files(self) -> List[str]:
        return [
            os.path.join(os.path.dirname(__file__), '..', 'small-samples', 'javascript', 'file1.js'),
            os.path.join(os.path.dirname(__file__), '..', 'small-samples', 'javascript', 'file2.js'),
            os.path.join(os.path.dirname(__file__), '..', 'small-samples', 'javascript', 'file3.js'),
        ]

    def get_expected_relationships(self) -> List[Dict[str, Any]]:
        js_path = os.path.join('test', 'small-samples', 'javascript')
        file1_qname = os.path.join(js_path, 'file1.js')
        file2_qname = os.path.join(js_path, 'file2.js')
        file3_qname = os.path.join(js_path, 'file3.js')
        return [
            # file2.js
            # {'source': file2_qname, 'target': file1_qname, 'type': 'imports', 'count': 1, 'source_qname': file2_qname, 'target_qname': file1_qname}, # not implemented yet
            {'source': 'Car', 'target': 'Vehicle', 'type': 'inherits', 'count': 1, 'source_qname': 'file2.js:Car'},
            {'source': 'Car', 'target': 'Engine', 'type': 'instantiates', 'count': 1, 'source_qname': 'Car.constructor'},
            {'source': 'drive', 'target': 'start', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Vehicle.start'},
            {'source': 'drive', 'target': 'start_engine', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Engine.start_engine'},
            {'source': 'drive', 'target': 'helper_function', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive'},
            {'source': 'drive', 'target': 'get_identifier', 'type': 'calls', 'count': 1, 'source_qname': 'Car.drive', 'target_qname': 'Car.get_identifier'},
            {'source': 'Car', 'target': 'constructor', 'type': 'contains_method', 'count': 1, 'target_qname': 'Car.constructor'},
            {'source': 'Car', 'target': 'drive', 'type': 'contains_method', 'count': 1, 'target_qname': 'Car.drive'},
            {'source': 'Car', 'target': 'get_identifier', 'type': 'contains_method', 'count': 1, 'target_qname': 'Car.get_identifier'},
            # {'source': 'drive', 'target': 'MY_CONSTANT', 'type': 'references_variable', 'count': 1, 'source_qname': 'Car.drive'}, # not implemented yet
            
            # file3.js
            # {'source': file3_qname, 'target': file2_qname, 'type': 'imports', 'count': 1, 'source_qname': file3_qname, 'target_qname': file2_qname}, # not implemented yet
            {'source': 'Garage', 'target': 'Car', 'type': 'instantiates', 'count': 1, 'source_qname': 'Garage.service_car'},
            {'source': 'service_car', 'target': 'drive', 'type': 'calls', 'count': 1, 'source_qname': 'Garage.service_car', 'target_qname': 'Car.drive'},
            {'source': 'main', 'target': 'Garage', 'type': 'instantiates', 'count': 1},
            {'source': 'main', 'target': 'service_car', 'type': 'calls', 'count': 1, 'target_qname': 'Garage.service_car'},
        ]
