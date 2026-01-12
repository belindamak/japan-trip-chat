import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from openai import AzureOpenAI
try:
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
except ImportError:
    DefaultAzureCredential = None
    get_bearer_token_provider = None
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
import secrets

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# User credentials (In production, use a proper database)
# Password is 'family2025' - you can change this
USERS = {
    'family': generate_password_hash('family2025')
}

# Azure OpenAI Configuration
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "https://mak.openai.azure.com/")
deployment = os.getenv("DEPLOYMENT_NAME", "gpt-4.1-mini")
search_endpoint = os.getenv("AZURE_AI_SEARCH_ENDPOINT", "https://bmsearchnotfree.search.windows.net")
search_index = os.getenv("AZURE_AI_SEARCH_INDEX", "japantripindex")

# System prompt for the travel assistant
SYSTEM_PROMPT = """You are a travel assistant. Help me organize my trip itinerary by providing transportation options, dining suggestions, and sample costs based on the information I provide regarding flights, hotel reservations, locations, and activities.

## Instructions
- Use the flight information, hotel details, and key destination/activities provided to create a detailed day-by-day itinerary for my trip.
- Include the best transportation options (e.g., buses, trains, or rideshare services) to move between locations. Specify departure/arrival times (if applicable), costs, and the duration of travel.
- Suggest nearby restaurants or eateries aligned with the cuisine I specify and provide sample menu prices for them.
- If specific instructions are provided (e.g., my current location and desired meal type or activity), prioritize those in your response. Restrict dining suggestions within a walking distance of 15-20 minutes unless otherwise specified."""

def get_azure_openai_client():
    """Initialize Azure OpenAI client with API key"""
    api_key = os.getenv('AZURE_OPENAI_API_KEY')
    
    if not api_key:
        raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")
    
    # Create client without proxy settings (Render compatibility)
    import httpx
    http_client = httpx.Client()
    
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version='2024-05-01-preview',
        http_client=http_client
    )
    return client

@app.route('/')
def index():
    """Redirect to login if not authenticated, otherwise show chat"""
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and check_password_hash(USERS[username], password):
            session['user'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Handle user logout"""
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        user_message = data.get('message', '')
        chat_history = data.get('history', [])
        
        # Initialize Azure OpenAI client
        client = get_azure_openai_client()
        
        # Build messages array with system prompt and history
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        # Add chat history (last 10 messages)
        messages.extend(chat_history[-10:] if len(chat_history) > 10 else chat_history)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        # Determine authentication method based on available credentials
        search_api_key = os.getenv('AZURE_AI_SEARCH_API_KEY')
        
        if search_api_key:
            # Use API key authentication (for Render.com or other external hosting)
            search_auth = {
                "type": "api_key",
                "key": search_api_key
            }
        else:
            # Use managed identity (for Azure deployment)
            search_auth = {
                "type": "system_assigned_managed_identity"
            }
        
        # Call Azure OpenAI with Azure AI Search integration
        completion = client.chat.completions.create(
            model=deployment,
            messages=messages,
            max_tokens=3308,
            temperature=0.31,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            extra_body={
                "data_sources": [
                    {
                        "type": "azure_search",
                        "parameters": {
                            "endpoint": search_endpoint,
                            "index_name": search_index,
                            "authentication": search_auth
                        }
                    }
                ]
            }
        )
        
        assistant_message = completion.choices[0].message.content
        
        return jsonify({
            'response': assistant_message,
            'success': True
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

if __name__ == '__main__':
    # For development only - use a proper WSGI server for production
    app.run(debug=True, host='0.0.0.0', port=8000)
