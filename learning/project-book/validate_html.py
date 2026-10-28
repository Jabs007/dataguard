import sys

def validate_html(file_path):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        # Basic validation - check for proper opening and closing tags
        if '<html>' not in content or '</html>' not in content:
            print("ERROR: Missing html tags")
            return False
        if '<html>' in content and '</html>' in content:
            print("HTML appears to be well-formed")
            return True
        else:
            print("ERROR: Malformed HTML structure")
            return False
    except Exception as e:
        print(f"Error reading file: {e}")
        return False

if __name__ == "__main__":
    valid = validate_html('index.html')
    print("HTML validation:", "PASS" if valid else "FAIL")
