"""Country code mapping for HomGar/RainPoint integration."""

# Map ISO 3166-1 alpha-2 country codes to phone country codes
COUNTRY_TO_PHONE_CODE = {
    "US": "1",      # United States
    "CA": "1",      # Canada
    "GB": "44",     # United Kingdom
    "AU": "61",     # Australia
    "NZ": "64",     # New Zealand
    "ZA": "27",     # South Africa
    "DE": "49",     # Germany
    "FR": "33",     # France
    "IT": "39",     # Italy
    "ES": "34",     # Spain
    "NL": "31",     # Netherlands
    "BE": "32",     # Belgium
    "CH": "41",     # Switzerland
    "AT": "43",     # Austria
    "SE": "46",     # Sweden
    "NO": "47",     # Norway
    "DK": "45",     # Denmark
    "FI": "358",    # Finland
    "PL": "48",     # Poland
    "CZ": "420",    # Czech Republic
    "IE": "353",    # Ireland
    "PT": "351",    # Portugal
    "GR": "30",     # Greece
    "RU": "7",      # Russia
    "CN": "86",     # China
    "JP": "81",     # Japan
    "KR": "82",     # South Korea
    "IN": "91",     # India
    "BR": "55",     # Brazil
    "MX": "52",     # Mexico
    "AR": "54",     # Argentina
    "CL": "56",     # Chile
    "CO": "57",     # Colombia
    "SG": "65",     # Singapore
    "MY": "60",     # Malaysia
    "TH": "66",     # Thailand
    "ID": "62",     # Indonesia
    "PH": "63",     # Philippines
    "VN": "84",     # Vietnam
    "IL": "972",    # Israel
    "AE": "971",    # United Arab Emirates
    "SA": "966",    # Saudi Arabia
    "TR": "90",     # Turkey
    "EG": "20",     # Egypt
    "NG": "234",    # Nigeria
    "KE": "254",    # Kenya
    "HK": "852",    # Hong Kong
    "TW": "886",    # Taiwan
}


def get_default_country_code(hass) -> str:
    """
    Get the default phone country code from Home Assistant configuration.
    
    Args:
        hass: Home Assistant instance
        
    Returns:
        Phone country code (e.g., "1" for US/CA, "44" for UK, "27" for ZA)
        Defaults to "27" (South Africa) if country not configured or not found
    """
    try:
        # Get the configured country from Home Assistant
        # Available since Home Assistant 2022.12
        country = hass.config.country
        
        if country and country in COUNTRY_TO_PHONE_CODE:
            return COUNTRY_TO_PHONE_CODE[country]
    except AttributeError:
        # hass.config.country not available in older HA versions
        pass
    
    # Default to South Africa (original default)
    return "27"
