import ast, pathlib
src = pathlib.Path("reports/realtor_agent.py").read_text()
ast.parse(src)
print("Syntax OK")
