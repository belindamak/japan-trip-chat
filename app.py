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

# Get username and password from environment variables
username = os.getenv('APP_USERNAME', 'family')
password = os.getenv('APP_PASSWORD', 'family2025')

# Debug logging (remove after testing)
print(f"DEBUG: Username from env: {username}")
print(f"DEBUG: Password length: {len(password)}")

USERS = {
    username: generate_password_hash(password)
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
        
        # Detect if this is a location-based query
        location_keywords = ['nearby', 'closest', 'near me', 'around here', 'close to', 'where i am', 'current location']
        is_location_query = any(keyword in user_message.lower() for keyword in location_keywords)
        
        # Detect if this needs general web search
        web_keywords = ['happening', 'events', 'news', 'current', 'today', 'this week', 'festival', 'weather', 'latest']
        needs_web_search = any(keyword in user_message.lower() for keyword in web_keywords)
        
        # Extract coordinates from message
        lat, lon = extract_location_from_message(user_message)
        
        # Initialize system content
        system_content = SYSTEM_PROMPT
        
        # Search nearby places if this is a location query with coordinates
        if is_location_query and lat and lon:
            # Extract what they're looking for (ramen, coffee, etc.)
            search_query = user_message.lower()
            
            # Remove location-related words to get the actual query
            for keyword in location_keywords + ['coordinates:', 'currently at:', 'what', 'where', 'find', 'are', 'there']:
                search_query = search_query.replace(keyword, '')
            
            search_query = search_query.strip()
            
            # Add context based on common patterns
            if 'restaurant' in search_query or 'food' in search_query or 'eat' in search_query:
                search_query = f"restaurants {search_query}"
            
            print(f"Searching Google Places for: '{search_query}' near {lat}, {lon}")
            places_info = search_nearby_places(lat, lon, search_query, radius=1500)
            
            if places_info:
                system_content += f"""

def search_web_google(query, num_results=5):
    """Search the web using Google Custom Search API"""
    try:
        api_key = os.getenv('GOOGLE_SEARCH_API_KEY')
        search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        
        if not api_key or not search_engine_id:
            return None
        
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': search_engine_id,
            'q': query,
            'num': num_results
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = []
            
            for item in data.get('items', [])[:5]:
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                results.append(f"**{title}**\n{snippet}\n")
            
            return "\n".join(results) if results else None
        else:
            print(f"Google Search error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error searching web: {e}")
        return None

if __name__ == '__main__':
    # For development only - use a proper WSGI server for production
    app.run(debug=True, host='0.0.0.0', port=8000)
