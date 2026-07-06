# Domain Events

Last Modified: 2026-03-26 | Code: APIDE

## Domain Event Basics

A **domain event** represents a change in the state of the domain of a software system. It captures something meaningful that has happened, such as a “Survey Saved” or “User Registered” event, and is used to trigger further actions or processes. Domain events enable a “decoupled” and event-driven architecture by allowing different parts of the system to respond to these events independently.

## Exporting Domain Events to Your Platform

By default, events in Shopmetrics are only emitted internally within the Shopmetrics platform. To build external integrations you will first need to decide which events you would like exported from the platform to your external platform that will handle the event and take action(s).

After deciding upon the events you need, you can then contact your Account Manager to have the platform configured to export those events to your platform whenever they occur in Shopmetrics.

**Note: Currently, only exporting to the following cloud platforms is supported. Exporting events to your own proprietary platform will be supported in a future release.**

**Supported Cloud Platforms:**

- Amazon EventBridge
- Amazon Simple Notification Service (Amazon SNS)
- Zapier Webhooks
- Google Cloud Pub / Sub
- Azure Service Bus
- Azure Event Grid
- n8n Webhook

## Domain Events available for export

In the table below you can find a list of domain events available for export from the platform to various external services. Here is a brief description of each column to clarify the information they contain:

- **Domain Event Object Name** – the object name of the domain event for export.
- **Domain Event Type**– the platform supports the following Domain Event Types:
  - **Base Domain Events** - automatically generated based on the Entity definition when an entity is created.
  - **Managed Domain Events** - emitted by managed code. These serve a more specialized business domain intent.
- **Record Operation Type** – identifies the kind of change - such as creation, modification, or deletion - that a domain event represents for a domain entity.
- **Entity** – the domain entity to which the domain event is related to

| Domain Event Object Name | Domain Event Type | Record Operation Type | Entity |
| --- | --- | --- | --- |
| ClientCustomProperty\_Created | Base | Created | Client Custom Properties |
| ClientCustomProperty\_Deleted | Base | Deleted | Client Custom Properties |
| ClientCustomProperty\_Updated | Base | Updated | Client Custom Properties |
| ClientReportingSetting\_Created | Base | Created | Reporting Settings (CX Analytics) |
| ClientReportingSetting\_Updated | Base | Updated | Reporting Settings (CX Analytics) |
| Client\_Created | Base | Created | Clients |
| Client\_Deleted | Base | Deleted | Clients |
| Client\_Updated | Base | Updated | Clients |
| CustomerJourney\_Created | Base | Created | Customer Journeys |
| CustomerJourney\_Deleted | Base | Deleted | Customer Journeys |
| CustomerJourney\_Updated | Base | Updated | Customer Journeys |
| Job\_Created | Base | Created | Jobs |
| Job\_Deleted | Base | Deleted | Jobs |
| Job\_Updated | Base | Updated | Jobs |
| JobReassigned | Managed | Created | Jobs |
| JobSubmitted | Managed | Created | Jobs |
| JobAssignedSaved | Managed | Created | Jobs |
| JobSubmittedSaved | Managed | Created | Jobs |
| JobStatusChanged | Managed | Updated | Jobs |
| JobPostedToJobBoard | Managed | Created | Jobs |
| JobApplicationReceived | Managed | Created | Jobs |
| JobApplicationApproved | Managed | Created | Jobs |
| JobApplicationSelfApproved | Managed | Created | Jobs |
| JobDeclined | Managed | Created | Jobs |
| JobLastActivityChanged | Managed | Updated | Jobs |
| LocationCustomPropertyValue\_Created | Base | Created | Location Custom Property Values |
| LocationCustomPropertyValue\_Deleted | Base | Deleted | Location Custom Property Values |
| LocationCustomPropertyValue\_Updated | Base | Updated | Location Custom Property Values |
| LocationGooglePlace\_Created | Base | Created | Location Google Places |
| LocationGooglePlace\_Deleted | Base | Deleted | Location Google Places |
| LocationGooglePlace\_Updated | Base | Updated | Location Google Places |
| LocationOnlineReview\_Created | Base | Created | Location Online Reviews |
| LocationOnlineReview\_Deleted | Base | Deleted | Location Online Reviews |
| LocationOnlineReview\_Updated | Base | Updated | Location Online Reviews |
| Location\_Created | Base | Created | Locations |
| Location\_Deleted | Base | Deleted | Locations |
| Location\_Updated | Base | Updated | Locations |
| SalesOrderLine\_Created | Base | Created | Sales Order Lines |
| SalesOrderLine\_Deleted | Base | Deleted | Sales Order Lines |
| SalesOrderLine\_Updated | Base | Updated | Sales Order Lines |
| SalesOrder\_Created | Base | Created | Sales Orders |
| SalesOrder\_Deleted | Base | Deleted | Sales Orders |
| SalesOrder\_Updated | Base | Updated | Sales Orders |
| SurveyForm\_Created | Base | Created | Survey Forms |
| SurveyForm\_Deleted | Base | Deleted | Survey Forms |
| SurveyForm\_Updated | Base | Updated | Survey Forms |
| SurveyForm\_EditQuestionChangeDataClassification | Managed | Created | Survey Forms |
| WorkOrderLine\_Created | Base | Created | Work Order Lines |
| WorkOrderLine\_Deleted | Base | Deleted | Work Order Lines |
| WorkOrderLine\_Updated | Base | Updated | Work Order Lines |
| WorkOrder\_Created | Base | Created | Work Orders |
| WorkOrder\_Deleted | Base | Deleted | Work Orders |
| User\_Created | Managed | Created | Users |
| User\_Updated | Managed | Updated | Users |

You can find more information about exporting Research Metrics Domain Events here:  
[Domain Events For Integration](https://shopmetrics.com/Website/pdf/Exporting-Research-Metrics-Domain-Events-For-Integration.pdf)
