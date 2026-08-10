# Stripe Integration Skill

## Overview
This skill provides MCP-compliant tools to interact with the Stripe API.

## Authentication
Required Auth: STRIPE_API_KEY
Alternatively, it looks for `os.environ.get("STRIPE_TEST_SECRET")`.

## Usage
Use this tool to construct valid API requests. Remember to always include the Bearer <STRIPE_TOKEN> in headers.
