from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('app/templates'))
try:
    template = env.get_template('debrief.html')
    print("Template parsed successfully.")
except Exception as e:
    print(f"Error: {e}")
