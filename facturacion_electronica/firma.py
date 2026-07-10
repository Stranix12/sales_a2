"""Firma electrónica *simulada* (XAdES-BES).

En producción el SRI exige firmar el XML con un certificado .p12 emitido por
una entidad certificadora, usando el estándar XAdES-BES. Aquí NO se firma de
verdad (no hay certificado ni se usa xmlsec, que traería librerías nativas
problemáticas en Render): se inserta un bloque ``<ds:Signature>`` con la forma
real pero con valores de marcador de posición, calculando un digest SHA-1 del
propio XML para que se vea consistente. Es un ejercicio académico."""
import base64
import hashlib

from lxml import etree

DS_NS = 'http://www.w3.org/2000/09/xmldsig#'


def firmar_xml_simulado(xml_str):
    """Devuelve el XML con un bloque <ds:Signature> (simulado) agregado."""
    root = etree.fromstring(xml_str.encode('utf-8'))

    # Digest SHA-1 del documento (como haría la firma real sobre el comprobante).
    digest = base64.b64encode(hashlib.sha1(xml_str.encode('utf-8')).digest()).decode()
    # "Firma" simulada: hash del digest, solo para tener un valor de aspecto real.
    firma_valor = base64.b64encode(
        hashlib.sha256((digest + 'SIMULADO').encode('utf-8')).digest()).decode()

    sig = etree.SubElement(root, '{%s}Signature' % DS_NS)
    sig.set('Id', 'SignatureSalesSystem')

    signed_info = etree.SubElement(sig, '{%s}SignedInfo' % DS_NS)
    etree.SubElement(signed_info, '{%s}CanonicalizationMethod' % DS_NS,
                     Algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
    etree.SubElement(signed_info, '{%s}SignatureMethod' % DS_NS,
                     Algorithm='http://www.w3.org/2000/09/xmldsig#rsa-sha1')
    ref = etree.SubElement(signed_info, '{%s}Reference' % DS_NS, URI='#comprobante')
    etree.SubElement(ref, '{%s}DigestMethod' % DS_NS,
                     Algorithm='http://www.w3.org/2000/09/xmldsig#sha1')
    etree.SubElement(ref, '{%s}DigestValue' % DS_NS).text = digest

    etree.SubElement(sig, '{%s}SignatureValue' % DS_NS).text = firma_valor

    key_info = etree.SubElement(sig, '{%s}KeyInfo' % DS_NS)
    x509 = etree.SubElement(key_info, '{%s}X509Data' % DS_NS)
    etree.SubElement(x509, '{%s}X509Certificate' % DS_NS).text = (
        'CERTIFICADO-SIMULADO-SALES-SYSTEM (ejercicio académico, sin validez legal)')

    return etree.tostring(root, pretty_print=True, xml_declaration=True,
                          encoding='UTF-8').decode('utf-8')
