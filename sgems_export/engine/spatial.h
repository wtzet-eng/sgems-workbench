#pragma once
#include <algorithm>
#include <cmath>
#include <vector>
struct Point { double x, y, z; };
double distance(Point a, Point b) {
    return std::hypot(std::hypot(a.x-b.x, a.y-b.y), a.z-b.z);
}
struct Sample {
    Point position;
    double value;
    Point location() const { return position; }
};
struct Neighbours : std::vector<Sample> {
    bool is_empty() const { return empty(); }
};
struct Spherical {
    double range;
    double operator()(Point a, Point b) const {
        double h = std::min(1.0, distance(a,b)/range);
        return (1-h)*(1-h)*(1+0.5*h);
    }
};
