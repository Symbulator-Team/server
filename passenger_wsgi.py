# Entry point for cPanel's "Setup Python App" (Phusion Passenger).
# cPanel looks for a module-level variable named `application`.
# Nothing else is needed here -- the whole app lives in app.py.
from app import app as application  # noqa: F401
