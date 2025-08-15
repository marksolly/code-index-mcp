# Developer's Guide to Adding a New Language

Language support in this project is test-driven. Before creating the logic that supports a language, you should create a test module for it.

## How to Add New Tests

To add tests for a new language (e.g., "Go"), a developer would follow these steps:

1.  **Add Code Samples**: Create a new directory `test/small-samples/go/` and add sample `.go` files that demonstrate the various relationship types (calls, imports, etc.). For languages with classes, mimicking the python example is recommended.

2.  **Create a Test Definition**: Create a new file `test/definitions/go.py`. In this file, define a `GoTestDefinition` class that inherits from `BaseTestDefinition`.

3.  **Specify Supported Relationships**: In the `GoTestDefinition` class, define the `supported_relationships` list. This list will contain the names of the relationship types that are applicable to Go. The definitive list of all possible relationship types can be found in `src/code_index_mcp/services/database.py`.

4.  **Define Expected Relationships**: For each sample file, specify the expected relationships that should be extracted by the indexer. This will be done in a structured way within the `GoTestDefinition` class.

5.  **Override Standard Tests (If Necessary)**: If a standard relationship test (e.g., `test_calls`) is not suitable for the new language, you can override it by defining a method with the same name in your `GoTestDefinition` class.

6.  **Add Custom Language-Specific Tests**: To add new tests that are unique to the language, simply add new methods to the `GoTestDefinition` class that start with `test_`. The test runner will automatically discover and execute them. For example, a `test_go_specific_feature()` method would be run as part of the test suite for Go.

7.  **Run the Tests**: The new tests for Go will be automatically discovered and executed the next time the test suite is run. No changes to the test runner will be needed.
