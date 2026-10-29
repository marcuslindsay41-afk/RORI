# Rori Restaurant Analytics API - n8n Integration Guide

This guide provides complete workflows for integrating Rori's restaurant analytics API with n8n automation platform.

**Containment notice:** operational recommendation endpoints, including both
analysis aliases and cached retrieval, are disabled with HTTP 503 /
`OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE`. Ingestion remains available but no
longer triggers recommendation analysis. Historical analysis workflow examples
below cannot enable operational recommendations.

## API Authentication

Data ingestion endpoints require API key authentication via header:
```
X-API-Key: test_key_1  # Restaurant 1
X-API-Key: test_key_2  # Restaurant 2
X-API-Key: test_key_3  # Restaurant 3
```

## Base Configuration

**API Base URL**: `http://127.0.0.1:8000`

**Content-Type**: `application/json`

**Available Endpoints**:
- `POST /data/pos` - Sales data ingestion
- `POST /data/inventory` - Inventory upserts
- `POST /data/labor` - Labor data insertion
- `POST /data/sync` - Combined data sync
- `POST /run-analysis/{restaurant_id}` - Disabled; returns the containment denial

---

## Workflow 1: POS Data Integration

### Overview
Automated daily sales data extraction from POS system to Rori analytics.

### n8n Workflow Steps

1. **HTTP Request Node**
   - **Method**: GET
   - **URL**: Your POS API endpoint
   - **Headers**: POS authentication headers
   - **Response**: Raw sales data

2. **Function Node (Transform POS Data)**
   ```javascript
   // Transform POS data to Rori format
   const transformData = (posData) => {
     return posData.map(item => ({
       date: item.date.split('T')[0], // Convert ISO date to YYYY-MM-DD
       item_name: item.productName,
       quantity_sold: item.quantity,
       revenue: item.totalAmount
     }));
   };
   
   return transformData($input.all());
   ```

3. **HTTP Request Node (Send to Rori)**
   - **Method**: POST
   - **URL**: `{{ $env.API_BASE_URL }}/data/pos`
   - **Headers**:
     ```json
     {
       "Content-Type": "application/json",
       "X-API-Key": "{{ $env.RESTAURANT_API_KEY }}"
     }
     ```
   - **Body**:
     ```json
     {
       "sales": {{ $json.transformedData }}
     }
     ```

4. **Error Handling**
   - Check response status code
   - Log failures to error tracking
   - Retry logic for failed requests

### Example Payload
```json
{
  "sales": [
    {
      "date": "2024-01-15",
      "item_name": "Burger",
      "quantity_sold": 25,
      "revenue": 125.50
    },
    {
      "date": "2024-01-15",
      "item_name": "Fries",
      "quantity_sold": 40,
      "revenue": 80.00
    }
  ]
}
```

### Expected Response
```json
{
  "status": "success",
  "rows_inserted": 2
}
```

---

## Workflow 2: Inventory Management

### Overview
Daily scheduled inventory synchronization from inventory management system.

### n8n Workflow Steps

1. **Schedule Trigger**
   - **Frequency**: Daily at 2:00 AM
   - **Timezone**: Restaurant local time

2. **HTTP Request Node (Fetch Inventory)**
   - **Method**: GET
   - **URL**: Your inventory system API
   - **Headers**: Inventory API authentication
   - **Response**: Current inventory levels

3. **Function Node (Transform Inventory)**
   ```javascript
   // Transform inventory data to Rori format
   const transformInventory = (inventoryData) => {
     return inventoryData.map(item => ({
       item_name: item.sku,
       quantity_in_stock: item.stockLevel,
       cost_per_unit: item.unitCost
     }));
   };
   
   return transformInventory($input.all());
   ```

4. **HTTP Request Node (Send to Rori)**
   - **Method**: POST
   - **URL**: `{{ $env.API_BASE_URL }}/data/inventory`
   - **Headers**:
     ```json
     {
       "Content-Type": "application/json",
       "X-API-Key": "{{ $env.RESTAURANT_API_KEY }}"
     }
     ```
   - **Body**:
     ```json
     {
       "inventory": {{ $json.transformedInventory }}
     }
     ```

5. **Success Notification**
   - Send email/Slack notification
   - Log to inventory sync dashboard

### Example Payload
```json
{
  "inventory": [
    {
      "item_name": "Burger Patty",
      "quantity_in_stock": 150,
      "cost_per_unit": 1.25
    },
    {
      "item_name": "Burger Buns",
      "quantity_in_stock": 200,
      "cost_per_unit": 0.15
    }
  ]
}
```

### Expected Response
```json
{
  "status": "success",
  "rows_updated": 2
}
```

---

## Workflow 3: Labor Data Integration

### Overview
Automated labor data extraction from scheduling/time tracking system.

### n8n Workflow Steps

1. **Schedule Trigger**
   - **Frequency**: Daily at 11:59 PM
   - **Purpose**: Capture complete day's labor data

2. **HTTP Request Node (Fetch Labor Data)**
   - **Method**: GET
   - **URL**: Your labor management API
   - **Parameters**: Date range for current day
   - **Response**: Daily labor summary

3. **Function Node (Transform Labor)**
   ```javascript
   // Transform labor data to Rori format
   const transformLabor = (laborData) => {
     return laborData.map(entry => ({
       date: entry.workDate.split('T')[0], // Convert to YYYY-MM-DD
       hours_worked: entry.totalHours,
       total_labor_cost: entry.laborCost
     }));
   };
   
   return transformLabor($input.all());
   ```

4. **HTTP Request Node (Send to Rori)**
   - **Method**: POST
   - **URL**: `{{ $env.API_BASE_URL }}/data/labor`
   - **Headers**:
     ```json
     {
       "Content-Type": "application/json",
       "X-API-Key": "{{ $env.RESTAURANT_API_KEY }}"
     }
     ```
   - **Body**:
     ```json
     {
       "labor": {{ $json.transformedLabor }}
     }
     ```

5. **Error Handling**
   - Validate required fields
   - Check for missing data
   - Alert on labor anomalies

### Example Payload
```json
{
  "labor": [
    {
      "date": "2024-01-15",
      "hours_worked": 8.5,
      "total_labor_cost": 127.50
    },
    {
      "date": "2024-01-15",
      "hours_worked": 7.25,
      "total_labor_cost": 108.75
    }
  ]
}
```

### Expected Response
```json
{
  "status": "success",
  "rows_inserted": 2
}
```

---

## Optional: Unified Sync Workflow

### Overview
Single workflow to sync all data types simultaneously using the combined endpoint.

### n8n Workflow Steps

1. **Schedule Trigger**
   - **Frequency**: Daily at 1:00 AM
   - **Purpose**: Complete data synchronization

2. **Parallel Data Fetching**
   - **Branch 1**: Fetch POS data (HTTP Request)
   - **Branch 2**: Fetch inventory data (HTTP Request)
   - **Branch 3**: Fetch labor data (HTTP Request)

3. **Data Transformation**
   - Transform each data type as shown above
   - Combine into single payload

4. **HTTP Request Node (Unified Sync)**
   - **Method**: POST
   - **URL**: `{{ $env.API_BASE_URL }}/data/sync`
   - **Headers**:
     ```json
     {
       "Content-Type": "application/json",
       "X-API-Key": "{{ $env.RESTAURANT_API_KEY }}"
     }
     ```
   - **Body**:
     ```json
     {
       "sales": {{ $json.transformedSales }},
       "inventory": {{ $json.transformedInventory }},
       "labor": {{ $json.transformedLabor }}
     }
     ```

### Expected Response
```json
{
  "status": "success",
  "sales_rows": 25,
  "inventory_rows": 15,
  "labor_rows": 7
}
```

---

## n8n Environment Variables

Set these in your n8n workflow environment:

```json
{
  "API_BASE_URL": "http://127.0.0.1:8000",
  "RESTAURANT_API_KEY": "test_key_1",
  "POS_API_URL": "https://your-pos-system.com/api/sales",
  "INVENTORY_API_URL": "https://your-inventory-system.com/api/items",
  "LABOR_API_URL": "https://your-labor-system.com/api/timesheets"
}
```

## Error Handling Best Practices

### Response Validation
```javascript
// Check HTTP response status
if ($response.statusCode !== 200) {
  throw new Error(`API request failed: ${$response.statusCode}`);
}

// Validate response body
const responseBody = JSON.parse($response.body);
if (responseBody.status !== 'success') {
  throw new Error(`API error: ${responseBody.detail}`);
}
```

### Retry Logic
- **Exponential backoff**: 1s, 2s, 4s, 8s
- **Max retries**: 3 attempts
- **Dead letter queue**: Failed requests for manual review

### Logging
- Log all API requests/responses
- Track transformation errors
- Monitor success/failure rates
- Alert on critical failures

## Testing the Integration

### Manual Testing
```bash
# Test POS endpoint
curl -X POST http://127.0.0.1:8000/data/pos \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test_key_1" \
  -d '{"sales": [{"date": "2024-01-15", "item_name": "Test Item", "quantity_sold": 10, "revenue": 50.0}]}'

# Test sync endpoint
curl -X POST http://127.0.0.1:8000/data/sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test_key_1" \
  -d '{"sales": [], "inventory": [], "labor": []}'
```

### Monitoring
- Recommendation analysis and retrieval return the containment denial; no GET analysis route exists.
- Successful ingestion does not create background recommendation logs.
- Monitor API response times
- Track data consistency

## Production Considerations

### Security
- Store API keys in n8n credentials (not environment variables)
- Use HTTPS in production
- Implement rate limiting
- Monitor for unauthorized access attempts

### Performance
- Batch data when possible (multiple items per request)
- Use background processing for large datasets
- Monitor API response times
- Implement caching for frequently accessed data

### Reliability
- Implement dead letter queues for failed requests
- Set up monitoring and alerting
- Regular backup of configuration
- Disaster recovery procedures

## Support

For issues with the integration:
1. Check API server status: `GET /health`
2. Verify API key validity
3. Review n8n execution logs
4. Test with manual API calls
5. Check Rori application logs

API documentation is available at: `http://127.0.0.1:8000/docs`
