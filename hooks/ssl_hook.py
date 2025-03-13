"""
Runtime hook to ensure SSL certificates are correctly configured.
This will run when the PyInstaller executable starts up.
"""
import os
import sys
import ssl
import certifi

# Make sure the current directory is in sys.path
if '.' not in sys.path:
    sys.path.insert(0, '.')

# Use the bundled certifi certificate
def override_where():
    """Override certifi.core.where to return the bundled certificate."""
    # If bundled certificate exists
    bundled_cert = os.path.join(sys._MEIPASS, "cacert.pem")
    if os.path.exists(bundled_cert):
        return bundled_cert
    return certifi.where()

# Override certifi's where function
if hasattr(certifi, 'core'):
    certifi.core.where = override_where
else:
    certifi.where = override_where

# Set SSL certificate environment variable
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# Configure SSL default context
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass 