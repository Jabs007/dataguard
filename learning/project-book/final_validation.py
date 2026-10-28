import html.parser

class SimpleHTMLValidator(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.errors = []
    
    def error(self, message):
        self.errors.append(message)
    
    def parse(self, file_path):
        with open(file_path, 'r') as f:
            self.feed(f.read())
    
    def validate(self):
        if self.errors:
            print("HTML validation errors:")
            for error in self.errors:
                print(f"  {error}")
            return False
        return True

validator = SimpleHTMLParser()
if validator.validate('index.html'):
    print("HTML validation: SUCCESS")
else:
    print("HTML validation: FAILED")
