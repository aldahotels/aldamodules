odoo.define("alda_helpdesk_pms.ticket_form", function () {
    "use strict";

    $(document).ready(function () {
        const locationSelect = document.querySelector("[name='location_type']");
        const roomField = document.querySelector("[name='room_ids']");

        if (!locationSelect || !roomField) {
            return;
        }

        const roomContainer = roomField.closest(".mb-3");
        if (!roomContainer) {
            return;
        }

        // Usamos una expresión de función para evitar problemas con no-inner-declarations
        const handleLocationChange = function () {
            const selectedValue = locationSelect.value.trim().toLowerCase();
            const isRoomOrBathroom = ["room", "bathroom"].includes(selectedValue);

            if (isRoomOrBathroom) {
                roomContainer.style.display = "block";
                roomField.required = true;
            } else {
                roomContainer.style.display = "none";
                roomField.required = false;
            }
            roomField.value = "";
        };

        handleLocationChange();
        $(locationSelect).on("change", handleLocationChange);

        // Filtro de tipos de ticket por equipo
        const teamSelect = document.querySelector("[name='team_id']");
        const typeSelect = document.querySelector("[name='ticket_type_id']");

        if (teamSelect && typeSelect) {
            const options = Array.from(typeSelect.querySelectorAll("option")).filter(
                (opt) => opt.dataset.teamId !== undefined
            );

            const filterTicketTypes = function () {
                const selectedTeam = teamSelect.value;

                options.forEach((option) => {
                    const teamId = option.dataset.teamId;
                    option.style.display =
                        !selectedTeam || teamId === selectedTeam ? "block" : "none";
                });
            };

            teamSelect.addEventListener("change", filterTicketTypes);
            filterTicketTypes();
        }
    });
});
