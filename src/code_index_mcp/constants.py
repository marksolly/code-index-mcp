"""
Shared constants for the Code Index MCP server.
"""

# Directory and file names
SETTINGS_DIR = "code_indexer"
CONFIG_FILE = "config.json"
INDEX_FILE = "index.json"

# Supported languages and their corresponding file extensions
SUPPORTED_LANGUAGES = {
    "python": [".py", ".pyw"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    # "c": [".c", ".h"],
    "cpp": [".cpp", ".hpp", ".cxx", ".cc", ".hxx", ".hh"],
    "c_sharp": [".cs"],
    "go": [".go"],
    # "objective-c": [".m", ".mm"],
    "ruby": [".rb"],
    "php": [".php"],
    "swift": [".swift"],
    # "kotlin": [".kt", ".kts"],
    "rust": [".rs"],
    # "scala": [".scala"],
    # "shell": [".sh", ".bash", ".zsh"],
    # "powershell": [".ps1"],
    # "batch": [".bat", ".cmd"],
    # "r": [".r", ".R"],
    # "perl": [".pl", ".pm"],
    # "lua": [".lua"],
    # "dart": [".dart"],
    # "haskell": [".hs"],
    # "ocaml": [".ml", ".mli"],
    # "fsharp": [".fs", ".fsx"],
    # "clojure": [".clj", ".cljs"],
    # "vim": [".vim"],
    # "zig": [".zig"],
    "html": [".html", ".htm"],
    "css": [".css", ".scss", ".sass", ".less", ".stylus", ".styl"],
    # "markdown": [".md", ".mdx"],
    # "json": [".json", ".jsonc"],
    # "xml": [".xml"],
    # "yaml": [".yml", ".yaml"],
    # "vue": [".vue"],
    # "svelte": [".svelte"],
    # "astro": [".astro"],
    # "handlebars": [".hbs", ".handlebars"],
    # "ejs": [".ejs"],
    # "pug": [".pug"],
    # "sql": [".sql", ".ddl", ".dml", ".mysql", ".postgresql", ".psql", ".sqlite", ".mssql", ".oracle", ".ora", ".db2", ".proc", ".procedure", ".func", ".function", ".view", ".trigger", ".index", ".migration", ".seed", ".fixture", ".schema"],
    # "nosql": [".cql", ".cypher", ".sparql"],
    # "graphql": [".gql"],
    # "migration_tools": [".liquibase", ".flyway"],
}

# Create a mapping from extension to language name
EXTENSION_TO_LANGUAGE = {ext: lang for lang, exts in SUPPORTED_LANGUAGES.items() for ext in exts}

# Supported file extensions for code analysis, derived from SUPPORTED_LANGUAGES
SUPPORTED_EXTENSIONS = list(EXTENSION_TO_LANGUAGE.keys())
