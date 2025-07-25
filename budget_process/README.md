# Hotel Budget Module

## Description

This module provides a foundation for budget management in hotels, allowing users to
create and manage budgets for different departments. It includes a base model that
contains common fields for budgets, as well as views that facilitate the visualization
and editing of data. The module integrates with the PMS (Property Management System) to
provide hotel-specific functionality.

## Features

- **Base Model**: 'budget.base', which includes fields for the responsible, description,
  account accounting, company, hotel, months and year.
- **Department Budget**: Models that inherit from 'budget.base' and are designed to
  manage budgets for different departments (FB, Marketing, IT, Operations, Revenue, TAZ,
  CFO, CAPEX, Controller, Hotels).
- **PMS Integration**: Integrates with PMS properties to automatically hotel
  information, including hotel codes and property details.
- **Views**: Includes tree, form, and pivot views to facilitate data visualization and
  management.
- **Automatic Total Calculation**: The total budget is automatically calculated based on
  the values entered for each month.
- **Security Groups**: Configurable access control with specific groups for managers and
  users.

## Dependencies

- `base` - Odoo base module
- `pms` - Property Management System module
- `account` - Accounting module

## Installation

1. Ensure that the PMS module is installed and configured with your hotel properties.
2. Clone the repository.
3. Place the module in the addons directory.
4. Install dependencies (base, pms, account).
5. Install the module through Odoo Apps or via command line.
6. Configure security groups and assign users as needed.

## Configuration

1. **PMS Properties**: Ensure your hotel properties are configured in the PMS module.
2. **Security Groups**: Assign users to appropriate budget groups (Budget Manager,
   Budget User).
3. **Companies**: Configure companies if using multi-company setup.

## Usage

1. Navigate to the Budget menu in Odoo.
2. Select the appropriate department (Hotels, FB, Marketing, etc.).
3. Create new budget entries by selecting the hotel property and entering monthly
   values.
4. The system will automatically calculate totals and populate hotel-related fields.

## License

AGPL-3

## Creator

Alexandra Suarez Graterol <saya.alex20@gmail.com>
