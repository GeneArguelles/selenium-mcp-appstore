from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "testplans" / "blazedemo_booking_smoke.jmx"


def _property(element: ET.Element, name: str) -> str | None:
    node = element.find(f"./stringProp[@name='{name}']")
    return (node.text or "") if node is not None else None


def _arguments(sampler: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for argument in sampler.findall(
        "./elementProp[@name='HTTPsampler.Arguments']/"
        "collectionProp[@name='Arguments.arguments']/elementProp"
    ):
        name = _property(argument, "Argument.name")
        value = _property(argument, "Argument.value")
        if name is not None and value is not None:
            result[name] = value
    return result


class BlazeDemoSmokePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = ET.parse(PLAN_PATH).getroot()

    def test_plan_has_bounded_public_target_profile(self) -> None:
        thread_group = self.root.find(".//ThreadGroup")
        self.assertIsNotNone(thread_group)
        assert thread_group is not None
        self.assertEqual(_property(thread_group, "ThreadGroup.num_threads"), "3")
        self.assertEqual(_property(thread_group, "ThreadGroup.ramp_time"), "6")
        self.assertEqual(_property(thread_group, "ThreadGroup.duration"), "90")
        self.assertEqual(
            thread_group.findtext(
                "./elementProp[@name='ThreadGroup.main_controller']/"
                "stringProp[@name='LoopController.loops']"
            ),
            "2",
        )
        self.assertEqual(
            thread_group.findtext("./boolProp[@name='ThreadGroup.scheduler']"),
            "true",
        )

        timer = self.root.find(".//ConstantTimer")
        self.assertIsNotNone(timer)
        assert timer is not None
        self.assertEqual(_property(timer, "ConstantTimer.delay"), "750")

    def test_http_defaults_are_property_constrained(self) -> None:
        defaults = self.root.find(".//ConfigTestElement")
        self.assertIsNotNone(defaults)
        assert defaults is not None
        self.assertEqual(
            _property(defaults, "HTTPSampler.domain"),
            "${__P(smoke_host,blazedemo.com)}",
        )
        self.assertEqual(
            _property(defaults, "HTTPSampler.protocol"),
            "${__P(smoke_protocol,https)}",
        )
        self.assertEqual(
            _property(defaults, "HTTPSampler.port"),
            "${__P(smoke_port,)}",
        )
        self.assertEqual(_property(defaults, "HTTPSampler.connect_timeout"), "3000")
        self.assertEqual(_property(defaults, "HTTPSampler.response_timeout"), "10000")

    def test_plan_models_four_request_booking_journey(self) -> None:
        samplers = self.root.findall(".//HTTPSamplerProxy")
        self.assertEqual(len(samplers), 4)
        actual = [
            (
                sampler.attrib["testname"],
                _property(sampler, "HTTPSampler.method"),
                _property(sampler, "HTTPSampler.path"),
            )
            for sampler in samplers
        ]
        self.assertEqual(
            actual,
            [
                ("01 Home page", "GET", "/"),
                ("02 Search Boston to London", "POST", "/reserve.php"),
                (
                    "03 Select demonstration flight",
                    "POST",
                    "/purchase.php",
                ),
                (
                    "04 Confirm synthetic purchase",
                    "POST",
                    "/confirmation.php",
                ),
            ],
        )
        for sampler in samplers:
            self.assertEqual(
                _property(sampler, "HTTPSampler.embedded_url_re"),
                "",
                f"{sampler.attrib['testname']} must not retrieve embedded resources",
            )

    def test_post_bodies_are_fixed_synthetic_demo_data(self) -> None:
        samplers = {
            sampler.attrib["testname"]: sampler
            for sampler in self.root.findall(".//HTTPSamplerProxy")
        }
        self.assertEqual(
            _arguments(samplers["02 Search Boston to London"]),
            {"fromPort": "Boston", "toPort": "London"},
        )
        self.assertEqual(
            _arguments(samplers["03 Select demonstration flight"]),
            {
                "fromPort": "Boston",
                "toPort": "London",
                "airline": "Virgin America",
                "flight": "43",
                "price": "472.56",
            },
        )
        confirmation = _arguments(samplers["04 Confirm synthetic purchase"])
        self.assertEqual(confirmation["inputName"], "PE Smoke Tester")
        self.assertEqual(confirmation["nameOnCard"], "PE Smoke Tester")
        self.assertEqual(confirmation["address"], "100 Test Avenue")
        self.assertEqual(confirmation["creditCardNumber"], "4111111111111111")

    def test_every_request_has_status_and_content_assertions(self) -> None:
        assertions = self.root.findall(".//ResponseAssertion")
        self.assertEqual(len(assertions), 8)
        fields = [
            _property(assertion, "Assertion.test_field") for assertion in assertions
        ]
        self.assertEqual(fields.count("Assertion.response_code"), 4)
        self.assertEqual(fields.count("Assertion.response_data"), 4)

        markers = {
            string.text
            for assertion in assertions
            if _property(assertion, "Assertion.test_field")
            == "Assertion.response_data"
            for string in assertion.findall(
                "./collectionProp[@name='Asserion.test_strings']/stringProp"
            )
        }
        self.assertEqual(
            markers,
            {
                "Welcome to the Simple Travel Agency!",
                "Flights from Boston to London",
                "Please submit the form below to purchase the flight.",
                "Thank you for your purchase today!",
            },
        )

    def test_plan_identifies_its_governed_client(self) -> None:
        headers = {
            _property(element, "Header.name"): _property(element, "Header.value")
            for element in self.root.findall(".//HeaderManager//elementProp")
        }
        self.assertEqual(
            headers["User-Agent"],
            "PersonaEngineering-JMeter-Smoke/1.0",
        )


if __name__ == "__main__":
    unittest.main()
