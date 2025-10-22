odoo.define("alda_helpdesk_pms.ticket_form", function () {
    "use strict";

    $(document).ready(function () {
        const priorityInput = document.getElementById("priority_value");
        const stars = document.querySelectorAll(".star-rating .star");

        if (priorityInput && stars.length) {
            const updateStars = (value) => {
                stars.forEach((s) => {
                    const starValue = parseInt(s.dataset.value, 10);
                    if (starValue <= value) {
                        s.innerHTML = "&#9733;";
                        s.classList.add("filled");
                    } else {
                        s.innerHTML = "&#9734;";
                        s.classList.remove("filled");
                    }
                });
            };

            updateStars(parseInt(priorityInput.value, 10) || 0);

            stars.forEach((star) => {
                star.addEventListener("click", function () {
                    const value = parseInt(this.dataset.value, 10);
                    const currentValue = parseInt(priorityInput.value, 10) || 0;

                    if (value === currentValue) {
                        priorityInput.value = 0;
                        updateStars(0);
                    } else {
                        priorityInput.value = value;
                        updateStars(value);
                    }
                });

                star.addEventListener("mouseover", function () {
                    const value = parseInt(this.dataset.value, 10);
                    updateStars(value);
                });

                star.addEventListener("mouseout", function () {
                    const currentValue = parseInt(priorityInput.value, 10) || 0;
                    updateStars(currentValue);
                });
            });
        }

        const locationSelect = document.querySelector("[name='location_type']");
        const roomField = document.querySelector("[name='room_ids']");

        if (!locationSelect || !roomField) {
            return;
        }

        const roomContainer = roomField.closest(".mb-3");
        if (!roomContainer) {
            return;
        }

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

        const teamSelect = document.querySelector("[name='team_id']");
        const typeSelect = document.querySelector("[name='ticket_type_id']");

        if (teamSelect && typeSelect) {
            const allOptions = Array.from(typeSelect.querySelectorAll("option"));

            const filterTicketTypes = function () {
                const selectedTeam = teamSelect.value;

                if (!selectedTeam) {
                    typeSelect.value = "";
                    typeSelect.disabled = true;
                    return;
                }

                typeSelect.disabled = false;

                allOptions.forEach((option) => {
                    const teamId = option.dataset.teamId;
                    if (option.value === "") {
                        option.hidden = false;
                    } else {
                        option.hidden = teamId !== selectedTeam;
                    }
                });

                const currentOption = typeSelect.options[typeSelect.selectedIndex];
                if (currentOption && currentOption.value && currentOption.hidden) {
                    typeSelect.value = "";
                }
            };

            teamSelect.addEventListener("change", filterTicketTypes);
            filterTicketTypes();
        }

        const locationFieldContainer = document.getElementById("location_field");
        const referenceFieldContainer = document.getElementById("reference_data_field");

        if (teamSelect && (locationFieldContainer || referenceFieldContainer)) {
            const handleTeamChange = function () {
                const selectedOption = teamSelect.options[teamSelect.selectedIndex];
                const requiresLocation =
                    selectedOption &&
                    selectedOption.dataset.requiresLocation === "True";

                if (locationFieldContainer) {
                    if (requiresLocation) {
                        locationFieldContainer.style.display = "block";
                        locationSelect.required = true;
                    } else {
                        locationFieldContainer.style.display = "none";
                        locationSelect.required = false;
                        locationSelect.value = "";
                    }
                }

                if (referenceFieldContainer) {
                    if (requiresLocation) {
                        referenceFieldContainer.style.display = "none";
                    } else {
                        referenceFieldContainer.style.display = "block";
                    }
                }
                if (referenceFieldContainer) {
                    if (!teamSelect.value || requiresLocation) {
                        referenceFieldContainer.style.display = "none";
                    } else {
                        referenceFieldContainer.style.display = "block";
                    }
                }
            };

            teamSelect.addEventListener("change", handleTeamChange);
            handleTeamChange();
        }
    });
});
