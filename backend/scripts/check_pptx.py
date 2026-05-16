try:
    from pptx import Presentation
    print("python-pptx is installed")
except ImportError as e:
    print(f"python-pptx not installed: {e}")
