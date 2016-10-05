"""
The module responsible for encoding/decoding RTMP amf messages.

This sub module contains classes/methods to establish a connection to a RTMP server,
and to read/write amf messages on a connected stream.
It also contains the PySocks (https://github.com/Anorov/PySocks) module to enable
a connection to a RTMP server using a proxy.
Socks.py has been modified.
"""

__author__ = 'nortxort'
__modified_by__ = 'Ruddernation Designs'
