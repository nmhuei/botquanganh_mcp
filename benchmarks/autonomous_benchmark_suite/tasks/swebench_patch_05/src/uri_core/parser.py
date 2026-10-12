import urllib.parse

def parse_url(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    
    # BUGGY: Fails on IPv6 hostnames like '[::1]' - doesn't strip brackets
    host = parsed.hostname
    port = parsed.port
    
    # Parse query params
    # BUGGY: When key ends with '[]' (e.g. tag[]=a&tag[]=b), it raises ValueError if not handled
    query_dict = {}
    if parsed.query:
        pairs = parsed.query.split("&")
        for pair in pairs:
            if not pair: continue
            k, v = pair.split("=", 1)
            k = urllib.parse.unquote(k)
            v = urllib.parse.unquote(v)
            if k.endswith("[]"):
                clean_k = k[:-2]
                if clean_k not in query_dict:
                    query_dict[clean_k] = []
                # BUG: If clean_k was previously set as a scalar, crash or overwrite!
                if not isinstance(query_dict[clean_k], list):
                    raise ValueError(f"Malformed bracket expression for key: {clean_k}")
                query_dict[clean_k].append(v)
            else:
                query_dict[k] = v
                
    return {
        "scheme": parsed.scheme,
        "netloc": parsed.netloc,
        "hostname": host,
        "port": port,
        "path": parsed.path,
        "query": query_dict
    }
