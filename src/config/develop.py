
from .production import defaults as production_defaults

defaults = production_defaults.copy()
defaults['host'] = 'test.faforever.com'
defaults['client/logs/console'] = True

# FIXME: Temporary fix for broken https config on test server
# Turns off certificate verification entirely
# import ssl
# ssl._https_verify_certificates(False)
