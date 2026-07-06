# Introduction to API v3

Last Modified: 2025-05-02 | Code: APIINV3

API v3 provides a streamlined way to access and manage your data by leveraging the Command and Query Separation (CQS) principle.

In API v3 data retrieval is handled through a dedicated query endpoint (/api/v3/query), using predefined Domain Queries for structured access. The payload for the requests is passed as a JSON object in the request body.

Modifying data is done via specific Command endpoints which execute predefined Domain Commands. The payload for the requests is passed as a JSON object in the request body.

## Testing and Consuming the API

API v3 is built using modern web standards and can be integrated with a variety of popular programming languages and frameworks. Whether you’re working with PowerShell, JavaScript/TypeScript, Python, Go, Ruby, Java, or modern environments like serverless platforms and containerized microservices, the API is designed to fit your development needs.

You can use API testing tools such as Postman or Insomnia for dynamic testing, debugging, and exploration. These tools allow you to simulate real-world scenarios, inspect API responses, and ensure your integrations perform as expected.

Every Shopmetrics platform instance has both a production and a “training” (sandboxed, non-production) site. Your Account Manager can provide you with the information for each. Using the training site, you can leverage the interactive API documentation and experiment with endpoints in real time to verify your requests are working as expected.
