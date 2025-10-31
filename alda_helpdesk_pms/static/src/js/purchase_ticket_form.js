odoo.define("alda_helpdesk_pms.purchase_ticket_form", function (require) {
    "use strict";
    const publicWidget = require("web.public.widget");
    const core = require("web.core");
    const _t = core._t;

    publicWidget.registry.PurchaseTicketForm = publicWidget.Widget.extend({
        selector: ".alda_purchase_ticket_form",
        events: {
            "change #num_products": "_onChangeNumProducts",
            "change input[type='file']": "_onFileChange",
            "show.bs.modal #staticBackdrop": "_onModalShow",
            submit: "_onSubmitForm",
        },

        start() {
            const numInput = this.el.querySelector("#num_products");
            const num = Math.min(Math.max(parseInt(numInput.value || 1, 10), 1), 10);
            this._savedFiles = new Map();
            this._renderProductRows(num);

            return this._super(...arguments);
        },

        _onFileChange(ev) {
            const input = ev.currentTarget;
            const file = input.files[0];
            const index = this._getInputIndex(input.name);

            this._updateFileFeedback(input, file);

            if (file) {
                if (index !== -1) {
                    this._savedFiles.set(`attachment${index}`, file);
                }
            } else if (index !== -1) {
                this._savedFiles.delete(`attachment${index}`);
            }
        },

        _updateFileFeedback(fileInput, file) {
            let feedbackContainer = null;
            const isMobile = window.innerWidth < 768;

            if (isMobile) {
                const parentP = fileInput.closest("p");
                if (parentP) {
                    feedbackContainer = parentP.querySelector(".file-feedback");
                    if (!feedbackContainer) {
                        feedbackContainer = document.createElement("small");
                        feedbackContainer.className =
                            "file-feedback text-success mt-1 d-block";
                        parentP.appendChild(feedbackContainer);
                    }
                }
            } else {
                const parentTd = fileInput.parentElement;
                if (parentTd) {
                    feedbackContainer = parentTd.querySelector(".file-feedback");
                    if (!feedbackContainer) {
                        feedbackContainer = document.createElement("small");
                        feedbackContainer.className =
                            "file-feedback text-success mt-1 d-block";
                        parentTd.appendChild(feedbackContainer);
                    }
                }
            }

            if (feedbackContainer) {
                if (file) {
                    feedbackContainer.textContent = `📎 ${this._escapeHtml(file.name)}`;
                    feedbackContainer.style.display = "block";
                } else {
                    feedbackContainer.textContent = "";
                    feedbackContainer.style.display = "none";
                }
            }
        },

        _getInputIndex(inputName) {
            const match = inputName.match(/\d+/);
            return match ? parseInt(match[0], 10) : -1;
        },

        _onChangeNumProducts(ev) {
            const num = Math.min(
                Math.max(parseInt(ev.currentTarget.value || 1, 10), 1),
                10
            );
            this._renderProductRows(num);
        },

        _onModalShow(ev) {
            if (!this._validateForm()) {
                ev.preventDefault();
                ev.stopImmediatePropagation();
                return false;
            }
            return true;
        },

        _validateForm() {
            const form = this.el;
            let isValid = true;

            const isMobile = window.innerWidth < 768;

            this._clearValidationErrors();

            const teamSelect = form.querySelector('select[name="team_id"]');
            if (!teamSelect || !teamSelect.value) {
                teamSelect.classList.add("is-invalid");
                this._addFieldError(teamSelect, _t("Select a department."));
                isValid = false;
            }

            const container = isMobile
                ? form.querySelector("#mobile_products_container")
                : form.querySelector("#products_container");

            const effectiveContainer = container || form;

            const numInput = form.querySelector("#num_products");
            const currentNum = Math.min(
                Math.max(parseInt(numInput.value || 1, 10), 1),
                10
            );

            for (let i = 0; i < currentNum; i++) {
                const productInput = effectiveContainer.querySelector(
                    `input[name="product_names${i}"]`
                );
                if (!productInput || !productInput.value.trim()) {
                    if (productInput) {
                        productInput.classList.add("is-invalid");
                        this._addFieldError(productInput, _t("Product is required."));
                    }
                    isValid = false;
                }

                const supplierInput = effectiveContainer.querySelector(
                    `input[name="suppliers${i}"]`
                );
                if (!supplierInput || !supplierInput.value.trim()) {
                    if (supplierInput) {
                        supplierInput.classList.add("is-invalid");
                        this._addFieldError(supplierInput, _t("Supplier is required."));
                    }
                    isValid = false;
                }

                const urlInput = effectiveContainer.querySelector(
                    `input[name="purchase_urls${i}"]`
                );
                if (!urlInput || !urlInput.value.trim()) {
                    if (urlInput) {
                        urlInput.classList.add("is-invalid");
                        this._addFieldError(urlInput, _t("Purchase URL is required."));
                    }
                    isValid = false;
                } else if (urlInput && !this._isValidUrl(urlInput.value)) {
                    urlInput.classList.add("is-invalid");
                    this._addFieldError(
                        urlInput,
                        _t("Enter a valid URL (https://...).")
                    );
                    isValid = false;
                }

                const quantityInput = effectiveContainer.querySelector(
                    `input[name="quantities${i}"]`
                );
                if (
                    !quantityInput ||
                    !quantityInput.value.trim() ||
                    isNaN(quantityInput.value) ||
                    parseInt(quantityInput.value, 10) < 1
                ) {
                    if (quantityInput) {
                        quantityInput.classList.add("is-invalid");
                        this._addFieldError(
                            quantityInput,
                            _t("Quantity must be a number greater than 0.")
                        );
                    }
                    isValid = false;
                }
            }

            if (!isValid) {
                this._showBootstrapAlert(
                    _t("Validation Error"),
                    _t(
                        "Please review the fields marked in red and correct the errors."
                    ),
                    "danger"
                );

                this._scrollToFirstError();
            }

            return isValid;
        },

        _clearValidationErrors() {
            const form = this.el;
            const invalidElements = form.querySelectorAll(".is-invalid");
            invalidElements.forEach((element) => {
                element.classList.remove("is-invalid");
            });

            const feedbacks = form.querySelectorAll(".js-field-feedback");
            feedbacks.forEach((fb) => fb.remove());
        },

        _addFieldError(inputElement, message) {
            try {
                const existing =
                    inputElement.parentElement.querySelector(".js-field-feedback");
                if (existing) {
                    existing.textContent = message;
                    return;
                }
                const feedback = document.createElement("div");
                feedback.className =
                    "js-field-feedback invalid-feedback d-block text-danger small mt-1";
                feedback.textContent = message;

                inputElement.parentElement.appendChild(feedback);
            } catch (e) {
                console.error("Error adding field feedback:", e);
            }
        },

        _isValidUrl(string) {
            try {
                new URL(string);
                return true;
            } catch (_) {
                return false;
            }
        },

        _scrollToFirstError() {
            const firstError = this.el.querySelector(".is-invalid");
            if (firstError) {
                firstError.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                });
                try {
                    firstError.focus();
                } catch (e) {
                    // Ignore
                }
            }
        },

        _renderProductRows(num) {
            const tbody = this.el.querySelector("#products_container");
            const mobileContainer = this.el.querySelector("#mobile_products_container");
            if (!tbody || !mobileContainer) return;
            const isMobile = window.innerWidth < 768;

            if (!this._savedRowsData) this._savedRowsData = {};

            const inputs = this.el.querySelectorAll(
                "input[name^='product_names'], input[name^='suppliers'], input[name^='purchase_urls'], input[name^='quantities'], input[name^='measurements']"
            );
            inputs.forEach((input) => {
                this._savedRowsData[input.name] = input.value;
            });

            this._cleanupFiles(num);

            if (isMobile) {
                mobileContainer.innerHTML = "";
            } else {
                tbody.innerHTML = "";
            }

            for (let i = 0; i < num; i++) {
                const productName = this._savedRowsData[`product_names${i}`] || "";
                const supplier = this._savedRowsData[`suppliers${i}`] || "";
                const purchaseUrl = this._savedRowsData[`purchase_urls${i}`] || "";
                const quantity = this._savedRowsData[`quantities${i}`] || "";
                const measurement = this._savedRowsData[`measurements${i}`] || "";
                const file = this._savedFiles.get(`attachment${i}`);

                if (isMobile) {
                    this._renderMobileRow(
                        mobileContainer,
                        i,
                        productName,
                        supplier,
                        purchaseUrl,
                        quantity,
                        measurement,
                        file
                    );
                } else {
                    this._renderDesktopRow(
                        tbody,
                        i,
                        productName,
                        supplier,
                        purchaseUrl,
                        quantity,
                        measurement,
                        file
                    );
                }
            }
        },

        _cleanupFiles(currentNum) {
            const filesToDelete = [];
            this._savedFiles.forEach((file, key) => {
                const index = this._getInputIndex(key);
                if (index >= currentNum) {
                    filesToDelete.push(key);
                }
            });

            filesToDelete.forEach((key) => {
                this._savedFiles.delete(key);
            });
        },

        _renderMobileRow(
            container,
            index,
            productName,
            supplier,
            purchaseUrl,
            quantity,
            measurement,
            file
        ) {
            const card = document.createElement("div");
            const productPlaceholder = _t("Product name");
            const supplierPlaceholder = _t("Supplier");
            const unitsPlaceholder = _t("Units");
            const measurementsPlaceholder = _t("Size, color, etc.");
            card.className = "mb-3 p-3 border rounded shadow-sm";
            card.innerHTML = `
                <p><strong>#:</strong> ${index + 1}</p>
                <p><strong>Product:</strong>
                    <input type="text" name="product_names${index}" value="${this._escapeHtml(
                productName
            )}" required="required" class="form-control mb-2" placeholder="${productPlaceholder}">
                </p>
                <p><strong>Supplier:</strong>
                    <input type="text" name="suppliers${index}" value="${this._escapeHtml(
                supplier
            )}" required="required" class="form-control mb-2" placeholder="${supplierPlaceholder}">
                </p>
                <p><strong>URL:</strong>
                    <input type="url" name="purchase_urls${index}" value="${this._escapeHtml(
                purchaseUrl
            )}" required="required" class="form-control mb-2" placeholder="${"https://example.com/product"}">
                </p>
                <p><strong>Units:</strong>
                    <input type="number" name="quantities${index}" value="${this._escapeHtml(
                quantity
            )}" required="required" class="form-control mb-2" min="1" placeholder="${unitsPlaceholder}" pattern="[0-9]*" inputmode="numeric">
                </p>
                <p><strong>Measurements:</strong>
                    <input type="text" name="measurements${index}" value="${this._escapeHtml(
                measurement
            )}" class="form-control mb-2" placeholder="${measurementsPlaceholder}">
                </p>
                <p><strong>Photo:</strong>
                    <input type="file" name="attachment${index}" accept="image/*" class="form-control attachment-input">
                    ${
                        file
                            ? `<small class="file-feedback text-success mt-1 d-block">📎 ${this._escapeHtml(
                                  file.name
                              )}</small>`
                            : '<small class="file-feedback" style="display: none;"></small>'
                    }
                </p>
            `;
            container.appendChild(card);
        },

        _renderDesktopRow(
            container,
            index,
            productName,
            supplier,
            purchaseUrl,
            quantity,
            measurement,
            file
        ) {
            const row = document.createElement("tr");
            const productPlaceholder = _t("Product name");
            const supplierPlaceholder = _t("Supplier");
            const unitsPlaceholder = _t("Units");
            const measurementsPlaceholder = _t("Size, color, etc.");
            row.innerHTML = `
                <td><input type="text" name="product_names${index}" value="${this._escapeHtml(
                productName
            )}" class="form-control" required="required" placeholder="${productPlaceholder}"></td>
                <td><input type="text" name="suppliers${index}" value="${this._escapeHtml(
                supplier
            )}" class="form-control" required="required" placeholder="${supplierPlaceholder}"></td>
                <td><input type="url" name="purchase_urls${index}" value="${this._escapeHtml(
                purchaseUrl
            )}" class="form-control" required="required" placeholder="${"https://example.com/product"}"></td>
                <td><input type="number" name="quantities${index}" value="${this._escapeHtml(
                quantity
            )}" class="form-control" required="required" min="1" placeholder="${unitsPlaceholder}" pattern="[0-9]*" inputmode="numeric"></td>
                <td><input type="text" name="measurements${index}" value="${this._escapeHtml(
                measurement
            )}" class="form-control" placeholder="${measurementsPlaceholder}"></td>
                <td>
                    <input type="file" name="attachment${index}" accept="image/*" class="form-control">
                    ${
                        file
                            ? `<small class="file-feedback text-success mt-1 d-block">📎 ${this._escapeHtml(
                                  file.name
                              )}</small>`
                            : '<small class="file-feedback" style="display: none;"></small>'
                    }
                </td>
            `;
            container.appendChild(row);
        },

        _escapeHtml(unsafe) {
            if (!unsafe) return "";
            return unsafe
                .replace(/&/g, "&amp;")
                .replace(/</g, "<")
                .replace(/>/g, ">")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        },

        async _onSubmitForm(ev) {
            ev.preventDefault();
            const form = ev.currentTarget;
            const formData = new FormData(form);

            const numInput = this.el.querySelector("#num_products");
            const currentNum = Math.min(
                Math.max(parseInt(numInput.value || 1, 10), 1),
                10
            );

            for (let i = 0; i < currentNum; i++) {
                const file = this._savedFiles.get(`attachment${i}`);
                if (file) {
                    formData.set(`attachment${i}`, file);
                }
            }

            console.log("🧾 Sending data form:");
            for (const [key, value] of formData.entries()) {
                console.log(`${key}:`, value instanceof File ? value.name : value);
            }

            try {
                const response = await fetch("/helpdesk/ticket/submit", {
                    method: "POST",
                    body: formData,
                });

                if (response.redirected) {
                    window.location.href = response.url;
                } else if (response.ok) {
                    const result = await response.json();
                    if (result.success) {
                        this._showBootstrapAlert(
                            _t("Success"),
                            _t("Ticket submitted successfully!"),
                            "success"
                        );
                    }
                }
            } catch (error) {
                this._showBootstrapAlert(
                    _t("Network Error"),
                    _t("Could not connect to the server."),
                    "danger"
                );
            }
        },

        _showBootstrapAlert(title, message, type = "info") {
            const alertContainer = this.el.querySelector("#alert-container");
            if (!alertContainer) {
                console.error(
                    "Alert container #alert-container not found in the widget's DOM."
                );
                return;
            }

            alertContainer.innerHTML = "";

            const alertDiv = document.createElement("div");
            alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
            alertDiv.setAttribute("role", "alert");
            alertDiv.innerHTML = `
                <strong>${this._escapeHtml(title)}</strong> ${this._escapeHtml(message)}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;

            alertContainer.appendChild(alertDiv);
        },
    });
});
