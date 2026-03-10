#!/usr/bin/env python3
"""
Start Flask API server with debugpy for VS Code debugging.
This allows you to set breakpoints in interactive_session.py and hit them during execution.
"""
import debugpy
from api_server import app

# Enable debugpy for VS Code debugging
debugpy.listen(("0.0.0.0", 5678))
print("🐛 Debugger listening on port 5678")
print("📌 You can now attach VS Code debugger")
print("   Use 'Attach to Running Flask Server' configuration")
print("")

# Wait for debugger to attach (optional - comment out to not wait)
# debugpy.wait_for_client()
# print("✓ Debugger attached!")

if __name__ == '__main__':
    print("Starting Eye Test API Server with debugging enabled...")
    print("Available endpoints:")
    print("  POST /api/session/start")
    print("  POST /api/session/<id>/respond")
    print("  POST /api/session/<id>/jump")
    print("  GET  /api/session/<id>/status")
    print("  POST /api/session/<id>/end")
    print("")
    print("Server running on http://0.0.0.0:5000")
    print("Debugger port: 5678")
    print("")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
