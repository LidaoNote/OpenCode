#!/usr/bin/env python3
import sys
import requests
import dns.message
import dns.rdatatype
import dns.query
import time

def test_doh_server(domain, doh_url):
    headers = {
        'Content-Type': 'application/dns-message'
    }
    
    # Create a DNS query for the domain
    query = dns.message.make_query(domain, dns.rdatatype.A)
    query_data = query.to_wire()
    
    try:
        start_time = time.time()  # Start timing
        response = requests.post(doh_url, headers=headers, data=query_data)
        end_time = time.time()  # End timing
        total_time_ms = (end_time - start_time) * 1000  # Calculate total time in milliseconds

        if response.status_code == 200:
            response_data = dns.message.from_wire(response.content)
            print(f"DoH server at {doh_url} is available.")
            for answer in response_data.answer:
                for item in answer.items:
                    print(f"{domain} resolves to {item}")
            print(f"Total query time: {total_time_ms:.2f} ms")
        else:
            print(f"DoH server at {doh_url} returned status code {response.status_code}.")
    except requests.RequestException as e:
        print(f"Failed to connect to DoH server at {doh_url}: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: doh.py <domain> <doh_url>")
        sys.exit(1)
    
    domain = sys.argv[1]
    doh_url = sys.argv[2]
    test_doh_server(domain, doh_url)
