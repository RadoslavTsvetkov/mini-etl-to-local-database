# Introduction to Command APIs for Project Setup and Management

Last Modified: 2025-04-17 | Code: APIPSI

The Command APIs for Project Setup and Management enable you to automate the entire process of preparing a client project — from creating client records to importing locations and configuring survey forms.

With these APIs, you can programmatically set up client data, import locations, and configure survey forms — covering all the essential steps needed to launch a new project or update an existing setup with minimal manual effort.

**What these APIs offer:**

- **Automation** – Eliminate repetitive manual tasks by triggering setup actions via API
- **Efficiency** – Accelerate project onboarding with a streamlined, structured setup process
- **Consistency** – Ensure standardized configurations across multiple client projects

**Included Command APIs:**

- Import Clients
- Import Locations
- Import Survey Forms
- Import Survey Form Structure

Each article in this series focuses on one of these endpoints, providing technical details and usage examples.

## User Security

To successfully use all Import Command APIs described in the "Command APIs for Project Setup and Management" series with a single user, we recommend that the user executing the requests has the following security settings in the Shopmetrics system:

- Membership in the "**Administrator - Restricted**" security role
- Membership in the "**Myst.Clients.CreateNewClient.Allow**" security group
- Valid **Client Credentials** for API authorization

For more information about granting restricted access to the system refer to the article "Grant Restricted Access to the System" (short code: **GRAS**).

For more information about the Client Credentials and API Authorization you can refer to the article “API Authorization” (short code: **APIAUT**)

**NOTE: Each article covering an individual Command API includes the minimum required user security settings needed to execute that specific endpoint.**
