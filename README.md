<div align="center">

<h1><a href="https://indiacompliance.app">India Compliance</a></h1>

Simple, yet powerful compliance solutions for Indian businesses

[![Server Tests](https://github.com/resilient-tech/india-compliance/actions/workflows/server-tests.yml/badge.svg)](https://github.com/resilient-tech/india-compliance/actions/workflows/server-tests.yml)
[![Codecov](https://codecov.io/gh/resilient-tech/india-compliance/branch/develop/graph/badge.svg)](https://codecov.io/gh/resilient-tech/india-compliance)

<br><br>
![image](https://github.com/resilient-tech/india-compliance/assets/16315650/f442f922-acd4-4676-9ae6-494b09242bdf)

</div>

## Introduction

India Compliance has been designed to make compliance with Indian rules and regulations simple, swift and reliable. To this end, it has been carefully integrated with GST APIs to simplify recurring compliance processes.

It builds on top of [ERPNext](https://github.com/frappe/erpnext) and the [Frappe Framework](https://github.com/frappe/frappe) - incredible FOSS projects built and maintained by the incredible folks at Frappe. Go check these out if you haven't already!

## Key Features

-   End-to-end GST e-Waybill management
-   Automated GST e-Invoice generation and cancellation
-   Advanced purchase reconciliation based on GSTR-2B and GSTR-2A
-   Autofill Party and Address details by entering their GSTIN
-   Configurable features based on business needs
-   Powerful validations to ensure correct compliance

For a detailed overview of these features, please [refer to the documentation](https://docs.indiacompliance.app/).

## Installation

### Docker

Use docker to deploy India Compliance in production. Use this [guide](https://github.com/frappe/frappe_docker/blob/main/docs/custom-apps.md) to deploy India Compliance by building your custom image.

<details>
<summary>Sample Apps JSON</summary>

`apps.json` could look like this for `version-15`:

```shell
export APPS_JSON='[
  {
    "url": "https://github.com/frappe/erpnext",
    "branch": "version-15"
  },
  {
    "url": "https://github.com/resilient-tech/india-compliance",
    "branch": "version-15"
  }
]'

export APPS_JSON_BASE64=$(echo ${APPS_JSON} | base64 -w 0)
```

</details>

### Manual
  
Once you've [set up a Frappe site](https://frappeframework.com/docs/v14/user/en/installation/), installing India Compliance is simple:

1.  Download the app using the Bench CLI.

    ```bash
    bench get-app --branch [branch name] https://github.com/resilient-tech/india-compliance.git
    ```

Replace `[branch name]` with the branch that you're using for Frappe Framework and ERPNext.
If it isn't specified, the `--branch` option will default to **develop**.

2.  Install the app on your site.

    ```bash
    bench --site [site name] install-app india_compliance
    ```

## In-app Purchases

Some of the automation features available in India Compliance require access to [GST APIs](https://discuss.erpnext.com/t/introducing-india-compliance/86335#a-note-on-gst-apis-3). Since there are some costs associated with these APIs, they can be accessed by signing up for an India Compliance Account after installing this app.

## Planned Features

-   Quick and easy filing process for GSTR-1 and GSTR-3B

## Contributing

-   [Issue Guidelines](https://github.com/frappe/erpnext/wiki/Issue-Guidelines)
-   [Pull Request Requirements](https://github.com/frappe/erpnext/wiki/Contribution-Guidelines)

## License

[GNU General Public License (v3)](https://github.com/resilient-tech/india-compliance/blob/develop/license.txt)
