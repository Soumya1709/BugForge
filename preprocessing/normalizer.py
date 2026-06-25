import ast
import textwrap

class CodeNormalizer(ast.NodeTransformer):
    def __init__(self):
        self.param_map = {}
        
    def visit_FunctionDef(self, node):
        node.name = "FUNC"
        self.param_map = {}
        
        for i,arg in enumerate(node.args.args, start=1):
            new_name = f"ARG{i}"
            self.param_map[arg.arg] = new_name
            arg.arg = new_name
            
        self.generic_visit(node)
        
        return node
    
    def visit_Name(self,node):
        if node.id in self.param_map:
            node.id = self.param_map[node.id]
            
        return node
    
def normalize(code):
        try:
            code = textwrap.dedent(code)
            tree=ast.parse(code)
            normalizer=CodeNormalizer()
            tree=normalizer.visit(tree)
            
            ast.fix_missing_locations(tree)
            
            return ast.unparse(tree)
        except SyntaxError as e:
            print("Syntax error:",e)
            return "PARSE_ERROR"
        
if __name__ == "__main__":
            
            code= """
            def calculate_customer_transaction_total(transactions):
                return sum(transactions)
            """
            
            normalized = normalize(code)
            
            print("Original Code:")
            print(code)
            print("\nNormalized Code:")
            print(normalized)
            
        