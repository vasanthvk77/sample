# Dynamic Form Integration Guide

This guide explains how to integrate the dynamic form generator into your existing `db_connection.ts` file.

## Changes Required

### 1. Replace the `getDynamicFormHTML` function

In your `db_connection.ts` file, locate the `getDynamicFormHTML` function (it should be around 500-1000 lines of hardcoded HTML).

**Replace it entirely** with the version from `db_connection_dynamic.ts`.

### 2. Add helper functions

Add these helper functions from `db_connection_dynamic.ts` after `getDynamicFormHTML`:

- `generateConnectionTypeToggle()`
- `generateFormFields()`
- `generateFormField()`
- `generateInputField()`
- `generatePasswordField()`
- `generateDropdownField()`
- `generateFileField()`
- `generateReadonlyField()`
- `generateSSLSection()`
- `generateProgressIndicator()`

### 3. Keep all existing logic

**DO NOT CHANGE** these parts of your `db_connection.ts`:

✅ Keep all imports and constants
✅ Keep `getSystemUsername()` function
✅ Keep `validateHostAddress()` function
✅ Keep `initializeSQLiteDB()` function
✅ Keep `getSQLiteDB()` function
✅ Keep `testDatabaseConnection()` function
✅ Keep `saveConnectionToSQLite()` function
✅ Keep `readConnectionsFromSQLite()` function
✅ Keep all state management functions
✅ Keep the `DBConnectionProvider` class
✅ Keep the `render()` method
✅ Keep all event handlers
✅ Keep the webview HTML template (in `panel.webview.html`)

### 4. Update the webview JavaScript

In the webview HTML section, ensure these JavaScript functions are present:

```javascript
// Add these to the <script> section in panel.webview.html

function toggleSSLFields() {
    const sslEnabled = document.getElementById('SSL_Enabled');
    const sslFieldsContainer = document.getElementById('sslFieldsContainer');
    
    if (sslEnabled && sslFieldsContainer) {
        sslFieldsContainer.style.display = sslEnabled.checked ? 'block' : 'none';
    }
}

function browseFile(fieldId) {
    vscode.postMessage({
        command: 'browseFile',
        fieldId: fieldId
    });
}
```

## File Structure After Integration

```
src/
├── db_connection.ts                 (7000 → 2000 lines)
│   ├── Imports & Constants
│   ├── Helper Functions (validation, etc.)
│   ├── getDynamicFormHTML()         ← NEW DYNAMIC VERSION
│   ├── generate*() helper functions ← NEW
│   ├── SQLite Functions
│   ├── Connection Functions
│   ├── DBConnectionProvider Class
│   └── Webview Logic
├── db_connection_form.json          ← UPDATED with field metadata
└── db_connection_dynamic.ts         ← REFERENCE (can be deleted after integration)
```

## Testing Checklist

After integration, test these scenarios:

- [ ] MySQL connection (host-based & JDBC URL)
- [ ] PostgreSQL connection with SSL enabled
- [ ] SQL Server with Windows Authentication
- [ ] Oracle with SID vs Service Name
- [ ] File-based databases (SQLite, DuckDB)
- [ ] Databricks with HTTP_Path
- [ ] Snowflake with Warehouse
- [ ] Form validation (required fields)
- [ ] Password show/hide toggle
- [ ] File browse button
- [ ] Connection type switching (Host ↔ JDBC URL)
- [ ] Authentication type switching
- [ ] SSL enable/disable
- [ ] Edit existing connection
- [ ] Reconnect to existing connection
- [ ] Delete connection

## Adding New Database Vendors

To add a new database vendor (e.g., "Cassandra"):

1. **Update `db_connection_form.json`** only:

```json
{
  "DB_Connection": {
    "Cassandra": {
      "DB_Vendor_Name": "Cassandra",
      "JDBC_URL_Template": "jdbc:cassandra://{host}:{port}/{keyspace}",
      "Connected_By_Options": ["Host-based connection", "JDBC URL connection"],
      "Default_Connected_By": "Host-based connection",
      "Fields": [
        {
          "name": "Name",
          "label": "Connection Name",
          "type": "text",
          "required": true,
          "placeholder": "Enter connection name",
          "order": 1
        },
        {
          "name": "Host",
          "label": "Host",
          "type": "text",
          "required": true,
          "placeholder": "127.0.0.1",
          "order": 2
        }
        // ... add more fields
      ],
      "SSL_Fields": [
        // ... add SSL fields if needed
      ]
    }
  }
}
```

2. **Update `database_master_config.json`** (backend):

Add connection pattern, parameter mapping, and transaction handling for the new vendor.

3. **Done!** The form will automatically appear in the UI.

## Benefits of Dynamic Approach

✅ **Reduced code size**: 7000 → 2000 lines  
✅ **Single source of truth**: All field definitions in JSON  
✅ **Easy to maintain**: Update JSON, not TypeScript  
✅ **Consistent UI**: All databases use same rendering logic  
✅ **Scalable**: Add new vendors without code changes  
✅ **Type-safe**: Field validation from JSON schema  
✅ **Flexible**: Support any field type (text, dropdown, file, etc.)  

## Troubleshooting

### Form not rendering
- Check console for errors
- Verify `dbTemplates` is loaded correctly
- Ensure JSON structure matches expected format

### Fields missing
- Check field `order` property
- Verify field names match TypeScript expectations
- Check `disabled_when` conditions

### SSL not working
- Verify `SSL_Fields` array in JSON
- Check `toggleSSLFields()` function is present
- Ensure SSL_Enabled checkbox exists

### File browse not working
- Check `browseFile()` function is present
- Verify `browseFile` message handler in extension
- Ensure file input type is set to "file"

## Migration Steps

1. **Backup** your current `db_connection.ts`
2. **Copy** functions from `db_connection_dynamic.ts`
3. **Replace** `getDynamicFormHTML` and add helpers
4. **Test** all database connections
5. **Verify** all features work (SSL, auth types, etc.)
6. **Delete** `db_connection_dynamic.ts` (reference only)

## Support

If you encounter issues:
1. Check the console for error messages
2. Verify JSON structure matches schema
3. Test with a simple database first (MySQL)
4. Gradually add complexity (SSL, auth types)
