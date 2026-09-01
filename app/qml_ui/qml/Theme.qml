import QtQuick

QtObject {
    id: theme

    property string variant: "classic"
    property string density: "compact"
    property real fontScale: 1.0

    readonly property bool lightMode: variant === "light"
    readonly property bool darkMode: variant === "dark"

    // Nebula Workbench: graphite surfaces, indigo-violet accent and semantic state.
    // "classic" is intentionally mapped to the dark workstation presentation.
    readonly property color window: lightMode ? "#F6F7FA" : darkMode ? "#08090D" : "#0A0B10"
    readonly property color chromeTop: lightMode ? "#F8F9FB" : "#10121A"
    readonly property color chromeBottom: lightMode ? "#F1F3F7" : "#0B0D12"
    readonly property color navigation: lightMode ? "#F8F9FB" : "#0D0F15"
    readonly property color navigationSelected: lightMode ? "#EEEFFF" : "#191B2A"
    readonly property color panel: lightMode ? "#FFFFFF" : "#101218"
    readonly property color panelRaised: lightMode ? "#FFFFFF" : "#151820"
    readonly property color panelDark: lightMode ? "#F1F3F6" : "#0C0E13"
    readonly property color inspector: lightMode ? "#FAFBFD" : "#0D0F14"
    readonly property color input: lightMode ? "#FFFFFF" : "#0F1117"
    readonly property color hover: lightMode ? "#ECEEF4" : "#171A22"
    readonly property color rowHover: hover
    readonly property color rowAlt: lightMode ? "#FAFBFC" : "#0D0F14"

    readonly property color border: lightMode ? "#D7DAE2" : "#252936"
    readonly property color borderStrong: lightMode ? "#B9BEC9" : "#373D4D"
    readonly property color borderDark: lightMode ? "#E6E8ED" : "#1B1E27"
    readonly property color text: lightMode ? "#161821" : "#F4F5F8"
    readonly property color textMuted: lightMode ? "#5F6673" : "#A4AABB"
    readonly property color textDim: lightMode ? "#8D93A0" : "#72798A"
    readonly property color disabledText: lightMode ? "#A8ADB7" : "#555C69"

    readonly property color accent: lightMode ? "#6668E8" : "#8587FF"
    readonly property color accentDark: lightMode ? "#5557D0" : "#6D70E8"
    readonly property color accentLight: lightMode ? "#8082F0" : "#A6A7FF"
    readonly property color accentSoft: lightMode ? "#ECECFF" : "#1A1B31"
    readonly property color selectionTop: navigationSelected
    readonly property color selectionBottom: navigationSelected

    readonly property color success: lightMode ? "#158653" : "#5AD69A"
    readonly property color warning: lightMode ? "#A56A0B" : "#E7B760"
    readonly property color error: lightMode ? "#C83E56" : "#FF7486"
    readonly property color info: lightMode ? "#376FD5" : "#78A8FF"

    readonly property color successBg: lightMode ? "#EAF7F0" : "#10241C"
    readonly property color warningBg: lightMode ? "#FFF5E2" : "#261E10"
    readonly property color errorBg: lightMode ? "#FFF0F3" : "#291418"
    readonly property color infoBg: lightMode ? "#EDF3FF" : "#121B2B"

    readonly property color shadow: lightMode ? "#18000000" : "#70000000"
    readonly property color scrim: lightMode ? "#70111218" : "#B0000000"

    readonly property int xxs: 2
    readonly property int xs: 4
    readonly property int sm: 8
    readonly property int md: 12
    readonly property int lg: 16
    readonly property int xl: 24
    readonly property int xxl: 32

    readonly property int rowHeight: density === "comfortable" ? 48 : 40
    readonly property int controlHeight: density === "comfortable" ? 42 : 36
    readonly property int headerHeight: density === "comfortable" ? 64 : 56
    readonly property int statusHeight: 0
    readonly property int navWide: 196
    readonly property int navCompact: 56
    readonly property int panelRadius: 12
    readonly property int smallRadius: 8
    readonly property int popupRadius: 14

    function font(basePixels) {
        var scaled = basePixels;
        if (basePixels <= 8) scaled = 12;
        else if (basePixels === 9) scaled = 13;
        else if (basePixels === 10) scaled = 14;
        else if (basePixels === 11) scaled = 15;
        else if (basePixels === 12) scaled = 16;
        else if (basePixels <= 16) scaled = basePixels + 2;
        return Math.max(10, Math.round(scaled * fontScale));
    }


    function toneColor(tone) {
        if (tone === "success") return success
        if (tone === "error") return error
        if (tone === "warning") return warning
        return info
    }

    function toneBackground(tone) {
        if (tone === "success") return successBg
        if (tone === "error") return errorBg
        if (tone === "warning") return warningBg
        return infoBg
    }
}
