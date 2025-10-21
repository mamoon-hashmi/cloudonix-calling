import os
import requests
import asyncio
import json
import logging

# Configure logging for better response output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def transfer_call(context, args):
    # Log the context object to debug its structure
    try:
        context_attrs = vars(context) if hasattr(context, '__dict__') else str(context)
        logger.info(f"Context object attributes: {context_attrs}")
    except Exception as e:
        logger.warning(f"Could not log context attributes: {str(e)}")

    # Retrieve Cloudonix configuration from environment variables
    bearer_token = os.environ.get('CLOUDONIX_API_KEY', '')
    transfer_number = os.environ.get('TRANSFER_NUMBER', '')
    trunk_name = os.environ.get('CLOUDONIX_TRUNK_NAME', '')
    domain_id = os.environ.get('CLOUDONIX_DOMAIN_ID', '')

    # Check if required environment variables are set
    if not all([bearer_token, transfer_number, trunk_name, domain_id]):
        logger.error("Missing required environment variables: CLOUDONIX_API_KEY, TRANSFER_NUMBER, CLOUDONIX_TRUNK_NAME, or CLOUDONIX_DOMAIN_ID")
        return "Error transferring call: Missing configuration"

    # Check for session token in context (try 'token' first, fallback to 'session')
    token = getattr(context, 'token', None)
    if not token:
        token = getattr(context, 'session', None)
    if not token:
        logger.error("No token or session found in context")
        return "Error transferring call: Missing session token"

    # Fetch session details from Cloudonix API
    session_url = f"https://api.cloudonix.io/customers/self/domains/{domain_id}/sessions/{token}"
    session_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}"
    }
    logger.info(f"Fetching session details from: {session_url}")

    try:
        session_response = requests.get(session_url, headers=session_headers)
        session_response.raise_for_status()
        session_data = session_response.json()
        logger.info(f"Session details fetched successfully. Response:\n{json.dumps(session_data, indent=2)}")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error fetching session: Status {e.response.status_code} - {e.response.text}")
        return f"Error fetching session details: HTTP {e.response.status_code} - {e.response.text}"
    except Exception as e:
        logger.error(f"General Error fetching session: {str(e)}")
        return f"Error fetching session details: {str(e)}"

    # Extract caller ID from session data
    caller_id = session_data.get('callerId', 'Unknown')

    # Construct caller name from session profile.trunk-sip-headers
    caller_name = 'R+Albright'
    try:
        profile = session_data.get('profile', {})
        sip_headers = profile.get('trunk-sip-headers', {})
        first_name = sip_headers.get('First-Name', '')
        last_name = sip_headers.get('Last-Name', '')
        caller_name = first_name if first_name else 'R+Albright'
        if last_name:
            caller_name += f" {last_name}"
    except Exception as e:
        logger.warning(f"Failed to extract caller name from session profile: {str(e)}")

    # Log final caller details
    logger.info(f"Final caller details - callerId: {caller_id}, callerName: {caller_name}")

    # Construct the Cloudonix API endpoint for transfer
    url = f"https://api.cloudonix.io/calls/{domain_id}/sessions/{token}/application"

    # CXML document to transfer the call with dynamic caller ID and name
    cxml_document = (
        f'<Response>'
        f'<Dial trunks="{trunk_name}" '
        f'callerId="{caller_id}" '
        f'callerName="{caller_name}">'
        f'{transfer_number}</Dial>'
        f'</Response>'
    )

    # Request payload
    payload = {
        "cxml": cxml_document
    }

    # Request headers
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}"
    }

    # Log the request details
    logger.info(f"Sending transfer request to: {url}")
    logger.info(f"Request payload: {json.dumps(payload, indent=2)}")
    logger.info(f"Request headers: {headers}")

    # Wait for 2 seconds before transferring the call
    await asyncio.sleep(2)

    try:
        # Send POST request to switch the voice application
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Pretty-print the API response
        try:
            response_json = response.json()
            logger.info(f"Transfer API Response (Status {response.status_code}):\n{json.dumps(response_json, indent=2)}")
        except ValueError:
            logger.info(f"Transfer API Response (Status {response.status_code}):\n{response.text}")
        
        return "Call transferred."
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error transferring call: Status {e.response.status_code}\n{json.dumps(e.response.json(), indent=2) if e.response.text else 'No response body'}")
        return f"Error transferring call: HTTP {e.response.status_code} - {e.response.text}"
    except Exception as e:
        logger.error(f"General Error transferring call: {str(e)}")
        return f"Error transferring call: {str(e)}"