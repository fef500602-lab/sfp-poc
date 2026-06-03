import os
from tree_sitter import Language, Parser
import tree_sitter_javascript as tsjavascript

lang = Language(tsjavascript.language())
parser = Parser()
parser.language = lang

def print_tree(node, indent=0):
    if indent > 5:
        return
    text = ""
    if node.child_count == 0 and node.text:
        text = repr(node.text.decode("utf-8")[:40])
    print(" " * indent + f"[{node.type}] {text}")
    for child in node.children:
        print_tree(child, indent + 2)

# Lista arquivos .js do React ordenados por tamanho
repo = "repos/realworld-react-js"
todos = []

for root_dir, dirs, files in os.walk(repo):
    dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "dist", "build"]]
    for filename in files:
        if filename.endswith(".js") or filename.endswith(".jsx"):
            filepath = os.path.join(root_dir, filename)
            size = os.path.getsize(filepath)
            todos.append((size, filepath))

todos.sort(reverse=True)
print("=== Arquivos JS/JSX por tamanho:\n")
for size, path in todos:
    print(f"  {size:6d} bytes — {path}")

# AST dos 2 maiores
print("\n=== AST dos 2 maiores:\n")
for size, filepath in todos[:2]:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()
    print(f"\n{'='*60}")
    print(f"Arquivo: {filepath} ({size} bytes)")
    print("Conteúdo (primeiras 25 linhas):")
    print("\n".join(code.split("\n")[:25]))
    print("\nAST:")
    tree = parser.parse(bytes(code, "utf-8"))
    print_tree(tree.root_node)