odoo.define("alda_helpdesk_pms.purchase_ticket_form", function (require) {
    "use strict";
    const publicWidget = require("web.public.widget");
    publicWidget.registry.PurchaseTicketForm = publicWidget.Widget.extend({
        selector: ".alda_purchase_ticket_form",
        events: {
            "change #num_products": "_onChangeNumProducts",
            submit: "_onSubmitForm",
        },
        start() {
            const numInput = this.el.querySelector("#num_products");
            const num = Math.min(Math.max(parseInt(numInput.value || 1, 10), 1), 10);
            this._renderProductRows(num);
            return this._super(...arguments);
        },
        _onChangeNumProducts(ev) {
            const num = Math.min(
                Math.max(parseInt(ev.currentTarget.value || 1, 10), 1),
                10
            );
            this._renderProductRows(num);
        },
        _renderProductRows(num) {
            const tbody = this.el.querySelector("#products_container");
            const mobileContainer = this.el.querySelector("#mobile_products_container");
            if (!tbody || !mobileContainer) return;
            const isMobile = window.innerWidth < 768;

            if (isMobile) {
                mobileContainer.innerHTML = "";
            } else {
                tbody.innerHTML = "";
            }

            for (let i = 0; i < num; i++) {
                if (isMobile) {
                    const card = document.createElement("div");
                    card.className = "mb-3 p-3 border rounded shadow-sm";
                    card.innerHTML = `
                        <p><strong>#:</strong> ${i + 1}</p>
                        <p><strong>Product:</strong> <input type="text" name="product_names${i}" required="required" class="form-control mb-2" placeholder="Product name"></p>
                        <p><strong>Supplier:</strong> <input type="text" name="suppliers${i}"required="required" class="form-control mb-2" placeholder="Supplier"></p>
                        <p><strong>URL:</strong> <input type="url" name="purchase_urls${i}" required="required" class="form-control mb-2" placeholder="https://example.com/product"></p>
                        <p><strong>Units:</strong> <input type="number" name="quantities${i}" required="required" class="form-control mb-2" min="1" placeholder="Units"></p>
                        <p><strong>Measurements:</strong> <input type="text" name="measurements${i}" class="form-control mb-2" placeholder="Size, color, etc."></p>
                        <p><strong>Photo:</strong> <input type="file" name="attachment${i}" accept="image/*" class="form-control"></p>
                    `;
                    mobileContainer.appendChild(card);
                } else {
                    const row = document.createElement("tr");
                    row.innerHTML = `
                        <td><input type="text" name="product_names${i}" class="form-control"  required="required" placeholder="Product name"></td>
                        <td><input type="text" name="suppliers${i}" class="form-control" required="required" placeholder="Supplier"></td>
                        <td><input type="url" name="purchase_urls${i}" class="form-control" required="required" placeholder="https://example.com/product"></td>
                        <td><input type="number" name="quantities${i}" class="form-control" required="required" min="1" placeholder="Units"></td>
                        <td><input type="text" name="measurements${i}" class="form-control" placeholder="Size, color, etc."></td>
                        <td><input type="file" name="attachment${i}" accept="image/*" class="form-control"></td>
                    `;
                    tbody.appendChild(row);
                }
            }
        },
        async _onSubmitForm(ev) {
            ev.preventDefault();
            const form = ev.currentTarget;
            const formData = new FormData(form);
            console.log("🧾 Enviando datos del formulario:");
            for (const [key, value] of formData.entries()) {
                console.log(`${key}:`, value);
            }
            try {
                const response = await fetch("/helpdesk/ticket/submit", {
                    method: "POST",
                    body: formData,
                    headers: {},
                });
                if (response.redirected) {
                    window.location.href = response.url;
                    return;
                }
            } catch (error) {
                this.displayNotification({
                    title: "Error de red",
                    message: "❌ No se pudo conectar con el servidor.",
                    type: "danger",
                });
            }
        },
    });
});
