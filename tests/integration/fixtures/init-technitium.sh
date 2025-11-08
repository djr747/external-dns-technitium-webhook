#!/bin/bash
# Initialize Technitium DNS with admin password and catalog zone
# Used by integration tests to set up Technitium in Kubernetes

set -e

TECHNITIUM_URL="${TECHNITIUM_URL:-http://technitium:5380}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD}"
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

# Attempt login with provided credentials
echo ""
echo "Logging in to Technitium with provided credentials..."
LOGIN_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/user/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "user=$ADMIN_USER&pass=$ADMIN_PASSWORD" 2>&1)

# Check if login was successful
if echo "$LOGIN_RESPONSE" | grep -q '"status":"ok"'; then
  echo "✓ Successfully authenticated with provided password"
  TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

  if [ -z "$TOKEN" ]; then
    echo "✗ ERROR: Could not extract authentication token"
    exit 1
  fi

  echo "✓ Token obtained: ${TOKEN:0:10}..."

  # Add user to DNS Administrators group
  echo "Adding user to DNS Administrators group..."
  GROUP_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/user/setUserGroup" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "token=$TOKEN&user=$ADMIN_USER&group=DNS Administrators" 2>&1)

  echo "Group change response: $GROUP_RESPONSE"

  if echo "$GROUP_RESPONSE" | grep -q '"status":"ok"'; then
    echo "✓ User added to DNS Administrators group"
  else
    echo "⚠ Failed to add user to DNS Administrators group: $GROUP_RESPONSE"
  fi
else
  echo "✗ ERROR: Could not authenticate to Technitium"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

# Create primary zone if specified
if [ -n "$ZONE" ]; then
  echo ""
  echo "Creating primary zone: $ZONE"
  PRIMARY_ZONE_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/zones/create" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "token=$TOKEN&zone=$ZONE&type=Primary" 2>&1)

  if echo "$PRIMARY_ZONE_RESPONSE" | grep -q '"status":"ok"'; then
    echo "✓ Primary zone created successfully"
  elif echo "$PRIMARY_ZONE_RESPONSE" | grep -q 'already exists'; then
    echo "ℹ Primary zone already exists (this is OK)"
  else
    echo "⚠ Primary zone creation response: $PRIMARY_ZONE_RESPONSE"
  fi
fi

# Create catalog zone
echo ""
echo "Creating catalog zone: $CATALOG_ZONE"
ZONE_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/zones/create" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$TOKEN&zone=$CATALOG_ZONE&type=Catalog" 2>&1)

if echo "$ZONE_RESPONSE" | grep -q '"status":"ok"'; then
  echo "✓ Catalog zone created successfully"
elif echo "$ZONE_RESPONSE" | grep -q 'already exists'; then
  echo "ℹ Catalog zone already exists (this is OK)"
else
  echo "⚠ Catalog zone creation response: $ZONE_RESPONSE"
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
echo "TECHNITIUM_USERNAME=$ADMIN_USER"
echo "TECHNITIUM_PASSWORD=$ADMIN_PASSWORD"
echo "TECHNITIUM_ZONE=$CATALOG_ZONE"
