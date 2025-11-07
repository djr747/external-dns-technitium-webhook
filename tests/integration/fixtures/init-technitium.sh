#!/bin/bash
# Initialize Technitium DNS with admin password and catalog zone
# Used by integration tests to set up Technitium in Kubernetes

set -e

TECHNITIUM_URL="${TECHNITIUM_URL:-http://technitium:5380}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(openssl rand -base64 12)}"
CATALOG_ZONE="${CATALOG_ZONE:-test.local}"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "========================================"
echo "Initializing Technitium DNS"
echo "========================================"
echo "URL: $TECHNITIUM_URL"
echo "User: $ADMIN_USER"
echo "Zone: $CATALOG_ZONE"
echo "========================================"

# Wait for Technitium API to be ready
echo "Waiting for Technitium API to be ready..."
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if curl -s -f "$TECHNITIUM_URL/api/user/login" > /dev/null 2>&1; then
    echo "✓ Technitium API is ready!"
    break
  fi
  RETRY_COUNT=$((RETRY_COUNT + 1))
  echo "  Attempt $RETRY_COUNT/$MAX_RETRIES: waiting..."
  sleep $RETRY_INTERVAL
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "✗ ERROR: Technitium API did not become ready after ${MAX_RETRIES} attempts"
  exit 1
fi

# Attempt login with admin/admin (default credentials)
echo ""
echo "Logging in to Technitium with default credentials..."
LOGIN_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/user/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "user=$ADMIN_USER&pass=admin" 2>&1)

# Check if login was successful
if echo "$LOGIN_RESPONSE" | grep -q '"status":"ok"'; then
  echo "✓ Successfully authenticated with default password"
  TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
  
  # Change password to the one we need
  if [ -n "$TOKEN" ] && [ "$ADMIN_PASSWORD" != "admin" ]; then
    echo ""
    echo "Changing admin password..."
    CHANGE_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/user/changePassword" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -H "Authorization: Bearer $TOKEN" \
      -d "user=$ADMIN_USER&newPassword=$ADMIN_PASSWORD" 2>&1)
    
    if echo "$CHANGE_RESPONSE" | grep -q '"status":"ok"'; then
      echo "✓ Password changed successfully"
    else
      echo "⚠ Password change may have failed, attempting to continue..."
    fi
  fi
else
  echo "⚠ Default login failed, attempting with configured password..."
  LOGIN_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/user/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "user=$ADMIN_USER&pass=$ADMIN_PASSWORD" 2>&1)
  
  if ! echo "$LOGIN_RESPONSE" | grep -q '"status":"ok"'; then
    echo "✗ ERROR: Could not authenticate to Technitium"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
  fi
  
  TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
  echo "✓ Successfully authenticated with configured password"
fi

if [ -z "$TOKEN" ]; then
  echo "✗ ERROR: Could not extract authentication token"
  exit 1
fi

echo "✓ Token obtained: ${TOKEN:0:10}..."

# Create catalog zone
echo ""
echo "Creating catalog zone: $CATALOG_ZONE"
ZONE_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/zones/createZone" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Bearer $TOKEN" \
  -d "zone=$CATALOG_ZONE&type=Primary" 2>&1)

if echo "$ZONE_RESPONSE" | grep -q '"status":"ok"'; then
  echo "✓ Zone created successfully"
elif echo "$ZONE_RESPONSE" | grep -q 'already exists'; then
  echo "ℹ Zone already exists (this is OK)"
else
  echo "⚠ Zone creation response: $ZONE_RESPONSE"
fi

echo ""
echo "========================================"
echo "Technitium initialization complete!"
echo "========================================"
echo "Admin User: $ADMIN_USER"
echo "Admin Password: $ADMIN_PASSWORD"
echo "Catalog Zone: $CATALOG_ZONE"
echo "API URL: $TECHNITIUM_URL"
echo "========================================"

# Export credentials for use by other containers
echo "TECHNITIUM_USERNAME=$ADMIN_USER" > /shared/technitium.env
echo "TECHNITIUM_PASSWORD=$ADMIN_PASSWORD" >> /shared/technitium.env
echo "TECHNITIUM_ZONE=$CATALOG_ZONE" >> /shared/technitium.env

echo ""
echo "Credentials saved to /shared/technitium.env"
cat /shared/technitium.env
