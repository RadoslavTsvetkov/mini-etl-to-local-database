# Introduction to Shopmetrics APIs

Last Modified: 2025-05-02 | Code: APIINT

This document explains how to integrate with the Shopmetrics platform via API endpoints. Included are various examples demonstrating how to read and write data.

---

**Read This First!**  
  
The Shopmetrics platform APIs are very powerful. Only experienced developers who are familiar with APIs and comfortable using them should utilize the Shopmetrics platform APIs.  
  
It is always recommended to test your API integrations with your Shopmetrics training website before integrating them with your production Shopmetrics data.  
  
**SUPPORT:** Use of the Shopmetrics platform APIs is offered on an “as-is” and “self-serve” basis. Support is available at hourly rates.  
  
**FAIR USE:**  
  
**-** Usage of the APIs may result in irreversible changes to your Shopmetrics platform data. Research Metrics shall not be held liable for any undesired results arising from use of the APIs.  
  
**-** Abuse of the APIs (for example, saturating the API with a high rate of consecutive API calls) is not permitted. Research Metrics reserves the right, in its sole discretion, to enforce limits and take any actions required to mitigate or eliminate such abuse, including but not limited to warning, suspension, and/or termination of access to the APIs.

---

## Command and Query APIs

The Shopmetrics Platform API is designed and built using the Command and Query Separation (CQS) principle. With CQS, every API call must either be a **command**that performs an action requesting a change the state of the application, or a **query**that returns data to the caller  but never both.

REST has been around since 2000. It has reshaped the way applications communicate on the web, replacing then-industry-standard protocols such as SOAP and COBRA. Today, REST is the dominant web communication protocol. However, its shortcomings have prompted the emergence of newer technologies that offer key improvements over REST. Examples of such new technologies are the graph-query languages for querying domain data such as GraphQL, Facebook's Graph API, Microsoft Graph, and more.

References:

- <https://graphql.org/>
- <https://www.freecodecamp.org/news/rest-apis-are-rest-in-peace-apis-long-live-graphql-d412e559d8e4/>
- <https://medium.com/@Niharika3297/time-for-rest-apis-to-rest-forever-%EF%B8%8F-all-hail-graphql-ecaec139ffe1>

References:

- (<https://en.wikipedia.org/wiki/Command%E2%80%93query_separation>).

The Shopmetrics APIs offer a Query API endpoint that exposes various query data models. The query data models expose internal graph or relational data structures. However, in the Shopmetrics Query API, these are generally flattened to reduce the complexity and learning curve of using the Shopmetrics API.

The two most important query data models in the Shopmetrics APIs are:

- Client Analytics query data model (used by Client Analytics)
- Operations query data model (used by the Survey Explorer)

Both offer rich filtering options and great flexibility for selecting specific fields to be retrieved.
