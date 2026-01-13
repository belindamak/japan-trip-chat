import os
import re
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
SYSTEM_PROMPT = """You are Smart Travel Buddy, a friendly AI-powered travel assistant specialized in helping with the user's Japan trip.

## Your Role
Help organize the trip itinerary by providing transportation options, dining suggestions, cost estimates, and personalized recommendations based on uploaded trip documents and real-time location data.

## Core Responsibilities
- Create detailed day-by-day itineraries using flight information, hotel details, and planned activities
- Provide transportation options (buses, trains, rideshare) with departure/arrival times, costs, and duration
- Suggest nearby restaurants aligned with cuisine preferences, including sample menu prices
- When given current location, prioritize nearby recommendations within 15-20 minutes walking distance
- Share key attractions, food recommendations, and cultural insights for destinations

## Response Guidelines
- Always respond in a friendly, conversational tone like a helpful travel guide
- Provide step-by-step guidance for travel planning
- Include practical examples with specific details (times, costs, distances)
- Summarize long answers with bullet points or day-wise itineraries
- If unsure, suggest possible options instead of saying "I don't know"
- When using real-time location data (Google Places), combine it with planned itinerary for personalized recommendations

## Current Context
You have access to the user's February 2025 Japan trip including:
- Flight schedules and airport information
- Hotel reservations and check-in/out details
- Planned activities, destinations, and attractions
- Restaurant recommendations and dining preferences
- Transportation routes and options

When users share their current location, provide nearby options that align with their trip style and schedule."""

def search_nearby_places(lat, lon, query, radius=1000):
    """Search for nearby places using Google Places API"""
    try:
        api_key = os.getenv('GOOGLE_PLACES_API_KEY')
        if not api_key:
            return None
        
        # Use Google Places API (New) - Text Search
        url = "https://places.googleapis.com/v1/places:searchText"
        
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.priceLevel,places.types,places.editorialSummary,places.currentOpeningHours'
        }
        
        body = {
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": lat,
                        "longitude": lon
                    },
                    "radius": radius
                }
            },
            "maxResultCount": 10,
            "languageCode": "en"
        }
        
        response = requests.post(url, headers=headers, json=body, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return format_places_results(data.get('places', []))
        else:
            print(f"Places API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error searching places: {e}")
        return None


def format_places_results(places):
    """Format Google Places results into readable text"""
    if not places:
        return None
    
    results = []
    for i, place in enumerate(places[:5], 1):  # Top 5 results
        name = place.get('displayName', {}).get('text', 'Unknown')
        address = place.get('formattedAddress', 'Address not available')
        rating = place.get('rating', 'N/A')
        rating_count = place.get('userRatingCount', 0)
        price_level = place.get('priceLevel', 'PRICE_LEVEL_UNSPECIFIED')
        
        # Convert price level
        price_map = {
            'PRICE_LEVEL_FREE': 'Free',
            'PRICE_LEVEL_INEXPENSIVE': '$',
            'PRICE_LEVEL_MODERATE': '$$',
            'PRICE_LEVEL_EXPENSIVE': '$$$',
            'PRICE_LEVEL_VERY_EXPENSIVE': '$$$$'
        }
        price = price_map.get(price_level, 'Price not available')
        
        # Check if open now
        opening_hours = place.get('currentOpeningHours', {})
        open_now = opening_hours.get('openNow', None)
        open_status = ''
        if open_now is not None:
            open_status = ' - 🟢 Open now' if open_now else ' - 🔴 Closed now'
        
        # Get editorial summary if available
        summary = place.get('editorialSummary', {}).get('text', '')
        
        result = f"{i}. **{name}**{open_status}\n"
        result += f"   - Rating: ⭐ {rating}/5 ({rating_count} reviews)\n"
        result += f"   - Price: {price}\n"
        result += f"   - Address: {address}\n"
        if summary:
            result += f"   - About: {summary}\n"
        
        results.append(result)
    
    return "\n".join(results)


def extract_location_from_message(message):
    """Extract coordinates from message"""
    import re
    
    # Look for coordinate pattern: "latitude, longitude"
    coord_pattern = r'(-?\d+\.\d+),\s*(-?\d+\.\d+)'
    match = re.search(coord_pattern, message)
    
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        return lat, lon
    
    return None, None

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

@app.route('/translate', methods=['POST'])
def translate():
    """Translate text to Japanese"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        text = data.get('text', '')
        
        client = get_azure_openai_client()
        
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are a translator. Translate the following English text to Japanese. Return ONLY the Japanese translation, nothing else."},
                {"role": "user", "content": text}
            ],
            max_tokens=200,
            temperature=0.3
        )
        
        translation = response.choices[0].message.content.strip()
        
        return jsonify({
            'translation': translation,
            'success': True
        })
        
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

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
            
            # Remove location-related words AND coordinates
            for keyword in location_keywords + ['coordinates:', 'currently at:', 'what', 'where', 'find', 'are', 'there', 'attractions']:
                search_query = search_query.replace(keyword, '')
            
            # Remove coordinate numbers (more aggressive cleaning)

            search_query = re.sub(r'-?\d+\.\d+', '', search_query)  # Remove coordinates
            search_query = re.sub(r'[,.]', ' ', search_query)  # Remove commas/periods
            search_query = ' '.join(search_query.split())  # Clean up extra spaces
            
            # If query is too short or generic, use default
            if len(search_query) < 3 or not search_query.strip():
                search_query = "restaurants"

            print(f"Searching Google Places for: '{search_query}' near {lat}, {lon}")
            places_info = search_nearby_places(lat, lon, search_query, radius=1500)
            
            if places_info:
                system_content += f"""

## Real-Time Nearby Options (from Google Places):
{places_info}

IMPORTANT INSTRUCTIONS:
- Use the Google Places data above to answer questions about what's currently nearby
- Cross-reference with the user's trip itinerary in your knowledge base
- Provide personalized recommendations that consider:
  1. Current nearby options (from Google above)
  2. The user's planned activities and schedule
  3. What fits their trip style and preferences
- Format your response naturally, don't just list the Google results
- Mention if any nearby places align with their itinerary
- Give your AI recommendation on which option is best for them
"""
        
        # Do general web search if needed (and not a location query)
        elif needs_web_search and not is_location_query:
            print(f"Searching web for: '{user_message}'")
            web_results = search_web_google(user_message)
            
            if web_results:
                system_content += f"""

## Current Web Information:
{web_results}

IMPORTANT INSTRUCTIONS:
- Use this current web information to supplement your knowledge
- Combine it with the user's trip itinerary
- Provide helpful, personalized recommendations
- Make sure information is relevant to their Japan trip
"""
        
        # Initialize Azure OpenAI client
        client = get_azure_openai_client()
        
        # Build messages array
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        # Add chat history (last 10 messages)
        messages.extend(chat_history[-10:] if len(chat_history) > 10 else chat_history)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        # Determine authentication method for Azure AI Search
        search_api_key = os.getenv('AZURE_AI_SEARCH_API_KEY')
        
        if search_api_key:
            search_auth = {
                "type": "api_key",
                "key": search_api_key
            }
        else:
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
        print(f"Error in chat: {str(e)}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

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
