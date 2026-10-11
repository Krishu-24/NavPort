/**
 * The API reference: Swagger UI rendering the API's OpenAPI description.
 *
 * The description is fetched from the API itself (GET /api/v1/openapi.json),
 * not copied into this site, so the reference always matches the API that is
 * actually deployed. Its server URL is relative, so "Try it out" sends each
 * request to that same API — cross-origin, allowed by the same CORS allowlist
 * that lets the dashboard in.
 */

import { apiUrl } from '/js/config.js';

const specUrl = apiUrl('/api/v1/openapi.json');
document.getElementById('spec-link').href = specUrl;

window.SwaggerUIBundle({
    url: specUrl,
    dom_id: '#swagger-ui',
    deepLinking: true,
    // Swagger UI would otherwise send the description to validator.swagger.io
    // to draw a badge — a third-party request this page has no need for.
    validatorUrl: null,
    docExpansion: 'list',
    defaultModelsExpandDepth: 0,
    displayRequestDuration: true,
    tryItOutEnabled: false,
});
