/* =========================================================
   INVENTORY MANAGEMENT SYSTEM
   DASHBOARD JAVASCRIPT
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    initSidebar();
    initTheme();

});


/* =========================================================
   SIDEBAR TOGGLE
========================================================= */

function initSidebar() {

    const menuButton = document.getElementById("menu-btn");
    const sidebar = document.getElementById("sidebar");

    if (!menuButton || !sidebar) {
        console.log("Sidebar elements not found");
        return;
    }

    menuButton.addEventListener("click", function (event) {

        event.preventDefault();
        event.stopPropagation();

        /*
         Desktop:
         Collapse sidebar and expand navbar/main content.
        */

        if (window.innerWidth > 991) {

            document.body.classList.toggle("sidebar-collapse");

            console.log(
                "Sidebar collapsed:",
                document.body.classList.contains("sidebar-collapse")
            );

        }

        /*
         Mobile:
         Open/close sidebar.
        */

        else {

            document.body.classList.toggle("sidebar-open");

        }

    });


    /*
     * Close mobile sidebar when clicking outside it.
     */

    document.addEventListener("click", function (event) {

        if (window.innerWidth > 991) {
            return;
        }

        if (
            document.body.classList.contains("sidebar-open") &&
            !sidebar.contains(event.target) &&
            !menuButton.contains(event.target)
        ) {

            document.body.classList.remove("sidebar-open");

        }

    });

}


/* =========================================================
   THEME SWITCHER
========================================================= */

const THEME_STORAGE_KEY = "ims-theme";


function getSavedTheme() {

    try {

        const theme =
            localStorage.getItem(THEME_STORAGE_KEY);

        if (
            theme === "light" ||
            theme === "dark" ||
            theme === "auto"
        ) {
            return theme;
        }

    } catch (error) {

        console.log("Could not read theme.");

    }

    return "light";
}


function systemPrefersDark() {

    return window.matchMedia(
        "(prefers-color-scheme: dark)"
    ).matches;

}


function resolveTheme(theme) {

    if (theme === "auto") {

        return systemPrefersDark()
            ? "dark"
            : "light";

    }

    return theme;

}


function applyTheme(theme) {

    const resolvedTheme =
        resolveTheme(theme);

    document.documentElement.setAttribute(
        "data-bs-theme",
        resolvedTheme
    );

    document.documentElement.style.colorScheme =
        resolvedTheme;

    updateThemeIcon(theme);

}


function updateThemeIcon(theme) {

    const themeButton =
        document.getElementById("theme-button");

    if (!themeButton) {
        return;
    }

    const icon =
        themeButton.querySelector("i");

    if (!icon) {
        return;
    }

    icon.classList.remove(
        "bi-sun-fill",
        "bi-moon-fill",
        "bi-circle-half"
    );

    if (theme === "dark") {

        icon.classList.add("bi-moon-fill");

    } else if (theme === "auto") {

        icon.classList.add("bi-circle-half");

    } else {

        icon.classList.add("bi-sun-fill");

    }

}


function setTheme(theme) {

    try {

        localStorage.setItem(
            THEME_STORAGE_KEY,
            theme
        );

    } catch (error) {

        console.log("Could not save theme.");

    }

    applyTheme(theme);

}


function initTheme() {

    const initialTheme =
        getSavedTheme();

    applyTheme(initialTheme);


    document.querySelectorAll(
        "[data-theme]"
    ).forEach(function (button) {

        button.addEventListener(
            "click",
            function () {

                const theme =
                    button.getAttribute("data-theme");

                if (
                    theme === "light" ||
                    theme === "dark" ||
                    theme === "auto"
                ) {

                    setTheme(theme);

                }

            }
        );

    });


    window.matchMedia(
        "(prefers-color-scheme: dark)"
    ).addEventListener(
        "change",
        function () {

            if (getSavedTheme() === "auto") {

                applyTheme("auto");

            }

        }
    );

}