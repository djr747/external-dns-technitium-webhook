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
while [[ $RETRY_COUNT -lt $MAX_RETRIES ]]; do
  if curl -s -f "$TECHNITIUM_URL/api/user/login" > /dev/null 2>&1; then
    echo "✓ Technitium API is ready!"
    break
  fi
  RETRY_COUNT=$((RETRY_COUNT + 1))
  echo "  Attempt $RETRY_COUNT/$MAX_RETRIES: waiting..."
  sleep $RETRY_INTERVAL
done

if [[ $RETRY_COUNT -eq $MAX_RETRIES ]]; then
  echo "✗ ERROR: Technitium API did not become ready after ${MAX_RETRIES} attempts" >&2
  exit 1
fi

# Attempt login with provided credentials
echo ""
echo "Logging in to Technitium with provided credentials..."
LOGIN_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/user/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "user=$ADMIN_USER" \
  --data-urlencode "pass=$ADMIN_PASSWORD" 2>&1)

# Check if login was successful
if echo "$LOGIN_RESPONSE" | grep -q '"status":"ok"'; then
  echo "✓ Successfully authenticated with provided password"
  TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

  if [[ -z "$TOKEN" ]]; then
    echo "✗ ERROR: Could not extract authentication token" >&2
    exit 1
  fi

  echo "✓ Token obtained: ${TOKEN:0:10}..."

  # Keep the built-in administrator group and grant DNS administration access.
  # Technitium v15 removed the former /api/user/setUserGroup endpoint; the
  # supported admin/users/set API replaces the user's complete group list.
  echo "Adding user to DNS Administrators group..."
  GROUP_RESPONSE=$(curl -sS --fail-with-body -X POST "$TECHNITIUM_URL/api/admin/users/set" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -H "Authorization: Bearer $TOKEN" \
    --data-urlencode "user=$ADMIN_USER" \
    --data-urlencode "memberOfGroups=Administrators,DNS Administrators" 2>&1) || {
      echo "✗ ERROR: Failed to add user to DNS Administrators group: $GROUP_RESPONSE" >&2
      exit 1
    }

  echo "Group change response: $GROUP_RESPONSE"

  if echo "$GROUP_RESPONSE" | grep -q '"status":"ok"'; then
    echo "✓ User added to DNS Administrators group"
  else
    echo "✗ ERROR: Failed to add user to DNS Administrators group: $GROUP_RESPONSE" >&2
    exit 1
  fi
else
  echo "✗ ERROR: Could not authenticate to Technitium" >&2
  echo "Response: $LOGIN_RESPONSE" >&2
  exit 1
fi

# Create primary zone if specified
if [[ -n "$ZONE" ]]; then
  echo ""
  echo "Creating primary zone: $ZONE"
  PRIMARY_ZONE_RESPONSE=$(curl -s -X POST "$TECHNITIUM_URL/api/zones/create" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "token=$TOKEN" \
    --data-urlencode "zone=$ZONE" \
    --data-urlencode "type=Primary" 2>&1)

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
  --data-urlencode "token=$TOKEN" \
  --data-urlencode "zone=$CATALOG_ZONE" \
  --data-urlencode "type=Catalog" 2>&1)

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
echo "Primary Zone: $ZONE"
echo "Catalog Zone: $CATALOG_ZONE"
echo "API URL: $TECHNITIUM_URL"
echo "========================================"
