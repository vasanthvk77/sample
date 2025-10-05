// Dynamic Database Connection Form Generator
// This file replaces the hardcoded form generation in db_connection.ts
// Uses db_connection_form.json for all field definitions

/**
 * Generate dynamic form HTML from JSON configuration
 * @param serverName - Database vendor name (e.g., "MySQL", "PostgreSQL")
 * @param values - Current form values
 * @param error - Error message to display
 * @param progress - Show progress indicator
 * @param progressMessage - Progress message text
 * @returns HTML string for the form
 */
function getDynamicFormHTML(
    serverName: string, 
    values: any = {}, 
    error: string = '', 
    progress: boolean = false, 
    progressMessage: string = ''
): string {
    console.log('[Dynamic Form] Generating form for:', serverName);
    
    // Get template from dbTemplates (loaded from db_connection_form.json)
    const template = dbTemplates[serverName];
    if (!template) {
        console.error('[Dynamic Form] No template found for:', serverName);
        return '<div style="color:#d73a49;padding:20px;">Template not found for ' + serverName + '</div>';
    }
    
    const connectedBy = values['Connected By'] || template['Default_Connected_By'] || 'Host-based connection';
    const jdbcUrl = values.JDBC_URL || template['JDBC_URL_Template'] || '';
    
    // Generate "Connected By" section
    const connectionTypeToggle = generateConnectionTypeToggle(template, connectedBy, jdbcUrl);
    
    // Generate form fields dynamically
    const formFields = generateFormFields(template, values, connectedBy);
    
    // Generate SSL section
    const sslSection = generateSSLSection(template, values);
    
    // Generate hidden fields
    const hiddenFields = `
        <input type="hidden" name="DB_Vendor_Name" value="${template.DB_Vendor_Name}">
        <input type="hidden" name="originalName" value="${values.Name || ''}">
    `;
    
    return `
        <div style="padding:16px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;">
                <button id="backToConnected" style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:#3c3c3c;color:#cccccc;border:1px solid #555;border-radius:4px;cursor:pointer;font-size:14px;transition:all 0.2s;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
                    </svg>
                    Back to Connected DBs
                </button>
                <div style="display:flex;align-items:center;gap:10px;">
                    <img src="${getDbImage(serverName)}" style="width:32px;height:32px;border-radius:4px;">
                    <span style="font-weight:bold;font-size:18px;color:#cccccc;">${serverName}</span>
                </div>
            </div>
            
            <div style="max-width:600px;margin:0 auto;">
                <div style="padding:24px;border:1px solid #3c3c3c;border-radius:8px;background:#252526;">
                    <div style="margin-bottom:20px;">
                        <div style="font-weight:bold;font-size:16px;color:#cccccc;margin-bottom:4px;">
                            ${values.Name ? 'Edit Connection' : 'New Connection'}
                        </div>
                        <div style="font-size:12px;color:#888;">
                            ${values.Name ? 'Update the connection details below' : 'Fill in the connection details below'}
                        </div>
                    </div>
                    <form id="dbForm">
                        ${connectionTypeToggle}
                        ${formFields}
                        ${sslSection}
                        ${hiddenFields}
                        <div style="display:flex;gap:12px;margin-top:24px;justify-content:space-between;align-items:center;">
                            <div id="connectionStatus" style="display:none;color:#007acc;font-size:14px;font-weight:500;">
                                <span id="statusText"></span>
                                <span id="statusDots" style="display:inline-block;">
                                    <span class="dot" style="animation-delay:0s;">.</span>
                                    <span class="dot" style="animation-delay:0.2s;">.</span>
                                    <span class="dot" style="animation-delay:0.4s;">.</span>
                                </span>
                            </div>
                            <div style="flex:1"></div>
                            <button type="submit" id="connectBtn" data-action="connect" style="padding:12px 20px;background:#007acc;color:#fff;border:none;border-radius:4px;font-weight:bold;cursor:pointer;font-size:14px;transition:all 0.2s;">
                                Connect
                            </button>
                        </div>
                        ${error ? `<div id="formError" style="color:#d73a49;margin-top:16px;padding:12px;background:#2d1b1b;border-radius:4px;font-size:12px;border-left:4px solid #d73a49;">${error}</div>` : ''}
                        ${progress ? generateProgressIndicator(progressMessage) : ''}
                    </form>
                </div>
            </div>
        </div>
    `;
}

/**
 * Generate "Connected By" toggle section
 */
function generateConnectionTypeToggle(template: any, connectedBy: string, jdbcUrl: string): string {
    const options = template['Connected_By_Options'] || ['Host-based connection', 'JDBC URL connection'];
    
    const radioButtons = options.map((option: string) => `
        <label style="display:flex;align-items:center;cursor:pointer;font-size:14px;color:#cccccc;">
            <input type="radio" name="Connected By" value="${option}" 
                   ${connectedBy === option ? 'checked' : ''} 
                   style="margin-right:8px;accent-color:#007acc;">
            ${option}
        </label>
    `).join('');
    
    const showJdbcUrl = connectedBy === 'JDBC URL connection';
    
    return `
        <div style="margin-bottom:24px;padding:20px;background:#252526;border:1px solid #3c3c3c;border-radius:8px;">
            <div style="font-weight:bold;font-size:16px;color:#cccccc;margin-bottom:16px;">Connected by</div>
            <div style="display:flex;gap:16px;margin-bottom:16px;">
                ${radioButtons}
            </div>
            <div id="jdbcUrlContainer" style="display:${showJdbcUrl ? 'block' : 'none'};">
                <label for="JDBC_URL" style="display:block;font-weight:bold;margin-bottom:8px;color:#cccccc;font-size:14px;">
                    JDBC URL *
                </label>
                <input type="text" id="JDBC_URL" name="JDBC_URL" value="${jdbcUrl}" 
                       placeholder="${template['JDBC_URL_Template'] || 'Enter JDBC URL'}"
                       style="width:100%;padding:12px;border:1px solid #3c3c3c;border-radius:4px;background:#1e1e1e;color:#cccccc;font-size:14px;box-sizing:border-box;">
                <div id="JDBC_URL_error" style="display:none;color:#ff6b6b;font-size:12px;margin-top:4px;padding:4px 8px;background:#2d1b1b;border:1px solid #ff6b6b;border-radius:4px;"></div>
            </div>
        </div>
    `;
}

/**
 * Generate form fields dynamically from JSON configuration
 */
function generateFormFields(template: any, values: any, connectedBy: string): string {
    const fields = template['Fields'] || [];
    
    // Sort fields by order
    const sortedFields = [...fields].sort((a, b) => (a.order || 999) - (b.order || 999));
    
    return sortedFields.map((field: any) => {
        return generateFormField(field, values, connectedBy, template);
    }).join('');
}

/**
 * Generate a single form field based on its configuration
 */
function generateFormField(field: any, values: any, connectedBy: string, template: any): string {
    const {
        name,
        label,
        type,
        required,
        placeholder,
        options,
        disabled_when,
        dynamic_label
    } = field;
    
    const value = values[name] || '';
    const isDisabled = disabled_when && connectedBy === disabled_when;
    const disabledAttr = isDisabled ? 'disabled' : '';
    const disabledStyle = isDisabled ? 'background:#2d2d2d;color:#666;cursor:not-allowed;' : '';
    const requiredMark = required ? ' *' : '';
    
    // Handle dynamic labels (e.g., Oracle SID/Service Name)
    let finalLabel = label;
    if (dynamic_label && name === 'Database') {
        const connectionType = values['Connection_Type'] || (template['Fields'].find((f: any) => f.name === 'Connection_Type')?.default) || 'SID';
        finalLabel = connectionType === 'SID' ? 'SID' : 'Service Name';
    }
    
    // Generate field based on type
    switch (type) {
        case 'text':
        case 'number':
            return generateInputField(name, finalLabel, type, value, placeholder, required, disabledAttr, disabledStyle, requiredMark);
        
        case 'password':
            return generatePasswordField(name, finalLabel, value, placeholder, required, disabledAttr, disabledStyle, requiredMark);
        
        case 'dropdown':
            return generateDropdownField(name, finalLabel, options || [], value, required, requiredMark);
        
        case 'file':
            return generateFileField(name, finalLabel, value, placeholder, required, disabledAttr, disabledStyle, requiredMark);
        
        case 'readonly':
            return generateReadonlyField(name, finalLabel, field.value || value);
        
        default:
            return '';
    }
}

/**
 * Generate standard input field (text/number)
 */
function generateInputField(
    name: string,
    label: string,
    type: string,
    value: any,
    placeholder: string,
    required: boolean,
    disabledAttr: string,
    disabledStyle: string,
    requiredMark: string
): string {
    return `
        <div style="margin-bottom:20px;">
            <label for="${name}" style="display:block;font-weight:bold;margin-bottom:8px;color:#cccccc;font-size:14px;">
                ${label}${requiredMark}
            </label>
            <input type="${type}" id="${name}" name="${name}" value="${value}" 
                   ${required ? 'required' : ''} placeholder="${placeholder || ''}" ${disabledAttr}
                   style="width:100%;padding:12px;border:1px solid #3c3c3c;border-radius:4px;background:#1e1e1e;color:#cccccc;font-size:14px;box-sizing:border-box;${disabledStyle}">
            <div id="${name}_error" style="display:none;color:#ff6b6b;font-size:12px;margin-top:4px;padding:4px 8px;background:#2d1b1b;border:1px solid #ff6b6b;border-radius:4px;"></div>
        </div>
    `;
}

/**
 * Generate password field with show/hide toggle
 */
function generatePasswordField(
    name: string,
    label: string,
    value: any,
    placeholder: string,
    required: boolean,
    disabledAttr: string,
    disabledStyle: string,
    requiredMark: string
): string {
    return `
        <div style="margin-bottom:20px;">
            <label for="${name}" style="display:block;font-weight:bold;margin-bottom:8px;color:#cccccc;font-size:14px;">
                ${label}${requiredMark}
            </label>
            <div style="position:relative;display:flex;align-items:center;">
                <input type="password" id="${name}" name="${name}" value="${value}" 
                       ${required ? 'required' : ''} placeholder="${placeholder || ''}" ${disabledAttr}
                       style="flex:1;padding:12px 45px 12px 12px;border:1px solid #3c3c3c;border-radius:4px;background:#1e1e1e;color:#cccccc;font-size:14px;box-sizing:border-box;${disabledStyle}">
                <button type="button" id="${name}_toggle" 
                        style="position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;color:#888;cursor:pointer;padding:4px;display:flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:4px;transition:all 0.2s ease;" 
                        title="Show password"
                        onmouseover="this.style.color='#ccc';this.style.backgroundColor='#333'" 
                        onmouseout="this.style.color='#888';this.style.backgroundColor='transparent'">
                    <svg id="${name}_eye" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                </button>
            </div>
            <div id="${name}_error" style="display:none;color:#ff6b6b;font-size:12px;margin-top:4px;padding:4px 8px;background:#2d1b1b;border:1px solid #ff6b6b;border-radius:4px;"></div>
        </div>
    `;
}

/**
 * Generate dropdown field
 */
function generateDropdownField(
    name: string,
    label: string,
    options: string[],
    value: any,
    required: boolean,
    requiredMark: string
): string {
    const optionsHtml = options.map(opt => 
        `<option value="${opt}" ${value === opt ? 'selected' : ''}>${opt}</option>`
    ).join('');
    
    return `
        <div style="margin-bottom:20px;">
            <label for="${name}" style="display:block;font-weight:bold;margin-bottom:8px;color:#cccccc;font-size:14px;">
                ${label}${requiredMark}
            </label>
            <select id="${name}" name="${name}" ${required ? 'required' : ''}
                    style="width:100%;padding:12px;border:1px solid #3c3c3c;border-radius:4px;background:#1e1e1e;color:#cccccc;font-size:14px;box-sizing:border-box;">
                ${optionsHtml}
            </select>
        </div>
    `;
}

/**
 * Generate file input field with browse button
 */
function generateFileField(
    name: string,
    label: string,
    value: any,
    placeholder: string,
    required: boolean,
    disabledAttr: string,
    disabledStyle: string,
    requiredMark: string
): string {
    return `
        <div style="margin-bottom:20px;">
            <label for="${name}" style="display:block;font-weight:bold;margin-bottom:8px;color:#cccccc;font-size:14px;">
                ${label}${requiredMark}
            </label>
            <div style="display:flex;gap:8px;">
                <input type="text" id="${name}" name="${name}" value="${value}" 
                       ${required ? 'required' : ''} placeholder="${placeholder || ''}" ${disabledAttr}
                       style="flex:1;padding:12px;border:1px solid #3c3c3c;border-radius:4px;background:#1e1e1e;color:#cccccc;font-size:14px;box-sizing:border-box;${disabledStyle}">
                <button type="button" onclick="browseFile('${name}')" 
                        style="padding:12px 16px;background:#007acc;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:14px;">
                    Browse
                </button>
            </div>
            <div id="${name}_error" style="display:none;color:#ff6b6b;font-size:12px;margin-top:4px;padding:4px 8px;background:#2d1b1b;border:1px solid #ff6b6b;border-radius:4px;"></div>
        </div>
    `;
}

/**
 * Generate readonly field
 */
function generateReadonlyField(name: string, label: string, value: any): string {
    return `
        <div style="margin-bottom:20px;">
            <label for="${name}" style="display:block;font-weight:bold;margin-bottom:8px;color:#cccccc;font-size:14px;">
                ${label}
            </label>
            <input type="text" id="${name}" name="${name}" value="${value}" readonly
                   style="width:100%;padding:12px;border:1px solid #3c3c3c;border-radius:4px;background:#1e1e1e;color:#888;font-size:14px;box-sizing:border-box;">
        </div>
    `;
}

/**
 * Generate SSL section with enable checkbox and fields
 */
function generateSSLSection(template: any, values: any): string {
    const sslFields = template['SSL_Fields'] || [];
    
    // If no SSL fields defined, return empty string
    if (sslFields.length === 0) {
        return '';
    }
    
    const sslEnabled = values.SSL_Enabled === true || values.SSL_Enabled === 'true';
    
    const sslFieldsHtml = sslFields.map((field: any) => {
        return generateFormField(field, values, '', template);
    }).join('');
    
    return `
        <div style="margin-bottom:20px;">
            <label style="display:flex;align-items:center;cursor:pointer;font-size:14px;color:#cccccc;">
                <input type="checkbox" id="SSL_Enabled" name="SSL_Enabled" 
                       ${sslEnabled ? 'checked' : ''} 
                       onchange="toggleSSLFields()" 
                       style="margin-right:8px;accent-color:#007acc;width:16px;height:16px;">
                <span style="font-weight:bold;">SSL Enable</span>
            </label>
        </div>
        <div id="sslFieldsContainer" style="display:${sslEnabled ? 'block' : 'none'};">
            ${sslFieldsHtml}
        </div>
    `;
}

/**
 * Generate progress indicator
 */
function generateProgressIndicator(message: string): string {
    return `
        <div id="formProgress" style="margin-top:16px;padding:16px;background:#1e3a8a;border-radius:4px;border-left:4px solid #3b82f6;">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
                <div class="spinner" style="width:20px;height:20px;border:2px solid #3b82f6;border-top:2px solid transparent;border-radius:50%;animation:spin 1s linear infinite;"></div>
                <span style="color:#93c5fd;font-size:14px;font-weight:500;">${message}</span>
            </div>
            <div style="width:100%;height:4px;background:#1e40af;border-radius:2px;overflow:hidden;">
                <div class="progress-bar" style="width:100%;height:100%;background:linear-gradient(90deg,#3b82f6,#60a5fa);animation:pulse 2s ease-in-out infinite;"></div>
            </div>
        </div>
        <style>
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            @keyframes pulse {
                0%, 100% { opacity: 0.6; }
                50% { opacity: 1; }
            }
        </style>
    `;
}

/**
 * JavaScript function to toggle SSL fields visibility
 * This is injected into the webview and called when SSL checkbox changes
 */
function toggleSSLFields() {
    const sslEnabled = document.getElementById('SSL_Enabled') as HTMLInputElement;
    const sslFieldsContainer = document.getElementById('sslFieldsContainer');
    
    if (sslEnabled && sslFieldsContainer) {
        sslFieldsContainer.style.display = sslEnabled.checked ? 'block' : 'none';
    }
}

/**
 * JavaScript function to handle file browsing
 * This is called when user clicks "Browse" button for file inputs
 */
function browseFile(fieldId: string) {
    // This sends a message to the extension host to open file dialog
    vscode.postMessage({
        command: 'browseFile',
        fieldId: fieldId
    });
}

// Export the main function for use in db_connection.ts
export { getDynamicFormHTML };
