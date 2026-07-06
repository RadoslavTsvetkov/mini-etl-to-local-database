# Introduction to Command APIs

Last Modified: 2025-10-02 | Code: APICMD

The **Shopmetrics Command API** **v2** enables changes to the state of data within the Shopmetrics Domain Model. All state changes are initiated through **Domain Command Requests**.

When you send a Domain Command Request:

- The API responds **synchronously** with a **Request ID**.
- The actual operation runs **asynchronously** in the background.

You can track progress or verify completion by checking the **status** of a Domain Command Request using its Request ID.
