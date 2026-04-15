# 4a. Execution Flow Document

This document explains how execution flows actively across the system runtime on the sample application.

## Node Provisioning and Routing
* **Provisioning Flow:** A new node connects, acquires an IP layout, downloads the system agent from the platform repo, and announces itself as healthy via Kafka.
* **Component Instantiation:** Upon assignment, the node runtime downloads an App Instance (e.g., the Sample App) and boots it inside its App Type Runtime (e.g., as a Python worker).
* **Routing Requests:**
  1. A client initiates a request (e.g., query standard endpoint).
  2. The **Request Dispatcher** interprets the domain/URL and queries the **HA/Load Balancer**.
  3. The request is proxied to the most available internal node executing that specific App component.

## Processing Execution 
Inside the application, execution involves:
* The input request hits the app framework routing map.
* The internal agent loads its context and interacts with attached tools.
* Sub-system calls (e.g., database updates or sending analytics) happen through the **Message Bus (Kafka)** by publishing to predefined topics where dedicated System Services listen.
* Real-time metrics flow seamlessly backward, captured by the Logging daemon without blocking the app's execution thread.
