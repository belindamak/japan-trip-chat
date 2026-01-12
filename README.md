# Japan Trip Chat - Azure Web App

A password-protected chat interface for your February 2025 Japan trip, powered by Azure OpenAI and Azure AI Search.

## Features

- 🔐 Password-protected access
- 🗾 AI travel assistant with your uploaded Japan trip data
- 💬 Clean, responsive chat interface
- 📱 Mobile-friendly design
- 🔍 Searches through your uploaded documents and itinerary

## Default Credentials

- **Username**: `family`
- **Password**: `family2025`

> ⚠️ **Important**: Change these credentials in production by editing the `USERS` dictionary in `app.py`

## Local Development Setup

### Prerequisites

- Python 3.9 or higher
- Azure CLI installed and logged in
- Access to your Azure subscription with the deployed resources

### Steps

1. **Clone or download this project**

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and update the values if needed (the defaults should work with your Azure setup).

5. **Login to Azure** (for managed identity authentication):
   ```bash
   az login
   ```

6. **Run the application**:
   ```bash
   python app.py
   ```

7. **Open your browser** and go to: `http://localhost:8000`

## Deploy to Azure App Service

### Option 1: Deploy via Azure Portal

1. **Create an Azure App Service**:
   - Go to Azure Portal
   - Create a new **Web App**
   - Choose:
     - Runtime: **Python 3.11**
     - Region: **East US** (same as your other resources)
     - Pricing: **Basic B1** or higher

2. **Enable Managed Identity**:
   - In your new App Service, go to **Identity**
   - Enable **System assigned** managed identity
   - Save and copy the Object (principal) ID

3. **Grant Permissions** (same as before):
   - Give the App Service's managed identity:
     - **Cognitive Services OpenAI User** role on your `mak` resource
     - **Search Index Data Reader** role on `bmsearchnotfree`
     - **Storage Blob Data Contributor** role on `bmstorageaz`

4. **Configure Environment Variables**:
   - In App Service, go to **Configuration** → **Application settings**
   - Add these settings:
     ```
     AZURE_OPENAI_ENDPOINT=https://mak.openai.azure.com/
     DEPLOYMENT_NAME=gpt-4.1-mini
     AZURE_AI_SEARCH_ENDPOINT=https://bmsearchnotfree.search.windows.net
     AZURE_AI_SEARCH_INDEX=japantripindex
     AZURE_COGNITIVE_SERVICES_RESOURCE=https://cognitiveservices.azure.com
     SECRET_KEY=<generate-a-random-key>
     ```

5. **Deploy the Code**:
   - Option A: Use VS Code Azure extension
   - Option B: Use Azure CLI:
     ```bash
     az webapp up --name your-app-name --resource-group foundry-rg --runtime "PYTHON:3.11"
     ```
   - Option C: Use GitHub Actions (see below)

### Option 2: Deploy via Azure CLI (Quickest)

```bash
# Login to Azure
az login

# Create the web app and deploy
az webapp up \
  --name japan-trip-chat-bee \
  --resource-group foundry-rg \
  --runtime "PYTHON:3.11" \
  --sku B1 \
  --location eastus

# Enable managed identity
az webapp identity assign \
  --name japan-trip-chat-bee \
  --resource-group foundry-rg

# Configure app settings
az webapp config appsettings set \
  --name japan-trip-chat-bee \
  --resource-group foundry-rg \
  --settings \
    AZURE_OPENAI_ENDPOINT="https://mak.openai.azure.com/" \
    DEPLOYMENT_NAME="gpt-4.1-mini" \
    AZURE_AI_SEARCH_ENDPOINT="https://bmsearchnotfree.search.windows.net" \
    AZURE_AI_SEARCH_INDEX="japantripindex" \
    AZURE_COGNITIVE_SERVICES_RESOURCE="https://cognitiveservices.azure.com" \
    SECRET_KEY="$(openssl rand -hex 32)"
```

Then grant the managed identity permissions as described above.

## Customization

### Change Login Credentials

Edit `app.py` and modify the `USERS` dictionary:

```python
USERS = {
    'yourfamily': generate_password_hash('your-secure-password'),
    'mom': generate_password_hash('mom-password'),
    'dad': generate_password_hash('dad-password'),
}
```

### Customize the Travel Assistant Prompt

Edit the `SYSTEM_PROMPT` variable in `app.py` to change how the AI responds.

### Change Styling

Edit the `<style>` sections in:
- `templates/login.html` - Login page styling
- `templates/chat.html` - Chat interface styling

## Troubleshooting

### "Unauthorized" Errors

- Make sure you're logged in with `az login`
- Verify managed identity has proper roles assigned
- Check that environment variables are set correctly

### Chat Not Responding

- Check App Service logs in Azure Portal
- Verify your Azure OpenAI deployment is active
- Ensure Azure AI Search index exists and has data

### Local Development Issues

- Make sure you're logged in to Azure CLI
- Check that you have permissions to access the resources
- Verify your `.env` file has correct values

## Security Notes

- The app uses managed identity for Azure authentication (no API keys in code)
- Session management with secure cookies
- Password hashing for user credentials
- In production, use HTTPS only
- Consider using Azure AD B2C for more robust authentication

## Cost Estimation

For low usage (family use):
- **App Service B1**: ~$13/month
- **Azure OpenAI**: Pay per token (~$0.50-2/month for light use)
- **Azure AI Search Free Tier**: $0
- **Storage**: ~$0.02/month

**Total**: Approximately $13-15/month

## Support

For issues or questions:
1. Check Azure App Service logs
2. Review the troubleshooting section
3. Check Azure resource status in the portal

---

Enjoy your Japan trip! 🗾✈️
