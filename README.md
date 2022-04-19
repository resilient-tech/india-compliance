<div align="center">
    <h1>
        <br>
        <a href="https://www.indiacompliance.app/">
            <img src="https://user-images.githubusercontent.com/54097382/163762588-0e1d9f20-bf81-451f-bfdc-dab3a6dcd324.jpg">
        </a>
    </h1>
</div>

<p align="center">ERPNext app to simplify compliance with Indian Rules and Regulations</p>

## Table of Contents
* [Installation](#installation)
* [Features](#initial-features)
* [Future Releases](#future-releases)
* [License](#license)

## Installation

You will need to simply install `india-compliance` app on your site along with **frappe** and **ERPNext**.

* Download and add application [india-compliance](https://github.com/resilient-tech/india-compliance/) to your bench using:<br>
`$ bench get-app [app-name] [app-link]`

* Install app on a particular site:<br>
`$ bench --site [site_name] install-app [app-name]`

## Initial Features

* Integrating GST Public APIs for simpler Party/ Address creation
![customer autofill|357x500](https://user-images.githubusercontent.com/54097382/163789992-cc954b43-b8c3-4625-b534-229ea8b49096.gif)
* Integrating e-Waybill APIs for end-to-end e-Waybill Management.
  * Creating e-Waybills
  * Updating transporter/ vehicle information
  * Cancelling e-Waybills
* Moved India-specific features into the new app.
* e-Invoicing feature
* India-specific configurations in GST Settings.

## Future Releases

* Purchase Reconciliation for GSTR-2A/GSTR-2B
* File GSTR-1 and GSTR-3B from ERP itself.

## License

GNU General Public License (v3)