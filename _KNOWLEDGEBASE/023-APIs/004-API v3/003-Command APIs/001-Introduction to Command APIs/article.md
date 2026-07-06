# Introduction to Command APIs

Last Modified: 2025-10-02 | Code: APICDV3

The **Shopmetrics Command API v3** provides functionality for modifying the state of data in the Shopmetrics Domain Model. All modifications are initiated through **Domain Command Requests**.

When a Domain Command Request is submitted:

- The API immediately returns a **Request ID**.
- The requested change is executed **asynchronously**in the background.

You can track progress or verify completion by checking the **status**of a Domain Command Request using its Request ID.
